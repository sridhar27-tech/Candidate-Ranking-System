import os
import re
import uuid
import asyncio
from typing import List, Dict, Any
import httpx
from fastapi import FastAPI, Body, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

# Pipeline Scoring Core Imports
from app.schemas import CandidateModel, JobDescriptionInput
from app.stage_1_skills import evaluate_semantic_skills
from app.stage_3_signals import calculate_platform_signals 
from app.agent_prompts import STAR_SCORING_PROMPT, AI_REASONING_PROMPT
from app.sandbox_jd_parser import run_pipeline

from fastapi.responses import StreamingResponse
from app.exporter import convert_rankings_to_csv_stream

app = FastAPI(title="Talent Context Ranker API (High-Speed Numerical Engine)")

# In-memory session store: { session_id -> { rankings, total_processed, created_at } }
# Avoids DB dependency while still enabling the leaderboard endpoint
_session_store: Dict[str, Any] = {}

# Enable CORS for frontend layout communications
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")


async def extract_star_score(candidate_payload: str) -> float:
    """
    Sends the candidate JSON summary to Qwen and forces it to yield a 
    single number, then extracts it safely using regex.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "prompt": f"System: {STAR_SCORING_PROMPT}\n\nUser Data:\n{candidate_payload}",
                    "stream": False,
                    "options": {
                        "num_predict": 10,     # Extremely low to make the response instant
                        "temperature": 0.0,    # 0.0 forces the model to be purely mathematical
                        "num_gpu": 99
                    }
                }
            )
            if response.status_code != 200:
                return 50.0 # Secure baseline fallback on inference slip
                
            raw_text = response.json().get("response", "").strip()
            
            # Use Regex to clean out anything that isn't a direct integer digit
            match = re.search(r'\d+', raw_text)
            if match:
                score = int(match.group())
                return min(max(score, 0), 100) # Clamp between 0 and 100 safely
            return 50.0
            
    except Exception:
        return 50.0 # Baseline fallback if local engine drops


async def generate_ai_reasoning(candidate_payload: str) -> str:
    """
    Calls the local LLM to produce a single-sentence insight about the candidate.
    Falls back to a generic sentence if the model fails.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "prompt": f"System: {AI_REASONING_PROMPT}\n\nCandidate Data:\n{candidate_payload}",
                    "stream": False,
                    "options": {
                        "num_predict": 60,   # Enough for one sentence
                        "temperature": 0.3,
                        "num_gpu": 99
                    }
                }
            )
            if response.status_code != 200:
                return "Insufficient data to generate a specific insight for this candidate."

            raw_text = response.json().get("response", "").strip()
            # Take only the first sentence in case the model outputs more
            sentence = raw_text.split(".")[0].strip()
            if sentence:
                return sentence + "."
            return "Insufficient data to generate a specific insight for this candidate."

    except Exception:
        return "Insufficient data to generate a specific insight for this candidate."



async def evaluate_and_rank_fast(
    job_description: JobDescriptionInput = Body(..., embed=True),
    candidates: List[CandidateModel] = Body(...)
):
    """
    High-Speed Stateless Evaluation: Accepts a structured JD JSON produced by the
    parser pipeline, condenses it into a focused semantic text, then evaluates all
    candidates via the C++ skills ranker + STAR behavioral LLM + platform signals.
    """
    if not candidates:
        raise HTTPException(status_code=400, detail="Candidate roster cannot be empty.")

    # Condense the structured JD JSON into a noise-free semantic evaluation string
    jd_evaluation_text = job_description.to_evaluation_text()
        
    evaluated_list = []
    
    for candidate in candidates:
        # Phase 1: Native C++ Core Module (Skills Match against condensed JD text)
        semantic_score = evaluate_semantic_skills(jd_evaluation_text, candidate.skills)
        
        # Phase 3: Platform Telemetry Signal Evaluation
        platform_score = calculate_platform_signals(candidate.redrob_signals)
        
        # -----------------------------------------------------------------
        # NEW HIGH-SPEED NUMERICAL STAR ANALYSIS
        # -----------------------------------------------------------------
        # Flatten candidate info into a clean, text-minimized JSON block for the prompt
        candidate_json_payload = candidate.json(include={'profile', 'career_history'})
        
        # Call local Qwen for the fast single-integer score
        behavioral_star_score = await extract_star_score(candidate_json_payload)

        # Generate a one-sentence AI reasoning insight for this candidate
        ai_reasoning = await generate_ai_reasoning(candidate_json_payload)
        
        # Comprehensive Aggregated Weight Matrix Calculation (40/40/20)
        # semantic_score (out of 100), behavioral_star_score (out of 100), platform_score (out of 100)
        composite_score = (semantic_score * 0.40) + (behavioral_star_score * 0.40) + (platform_score * 0.20)
        evaluated_list.append({
            "candidate_id": candidate.candidate_id,
            "final_score": round(composite_score, 2),
            "ai_reasoning": ai_reasoning,
            "breakdown": {
                "stage_1_skills_semantic": round(semantic_score, 2),
                "stage_2_behavioral_star": round(behavioral_star_score, 2), # Clean integer score
                "stage_3_platform_signals": round(platform_score, 2)
            }
        })
        
    # 1. Sort the entire candidate roster based on final scores (highest first)
    evaluated_list.sort(key=lambda x: x["final_score"], reverse=True)
    
    # 2. Append the absolute integer ranking order positions
    for index, record in enumerate(evaluated_list, start=1):
        record["rank"] = index

    # 3. Generate a unique session ID and persist rankings in-memory
    session_id = str(uuid.uuid4())
    _session_store[session_id] = {
        "rankings": evaluated_list,
        "total_processed": len(evaluated_list),
    }
        
    return {
        "status": "success",
        "session_id": session_id,
        "total_processed": len(evaluated_list),
        "rankings": evaluated_list
    }
@app.get("/api/rank/leaderboard/{session_id}")
async def get_leaderboard(session_id: str):
    """
    Retrieves previously evaluated rankings for a given session ID.
    Rankings are stored in-memory after /api/rank/evaluate is called.
    """
    session = _session_store.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found. It may have expired or the server was restarted."
        )
    return {
        "status": "success",
        "session_id": session_id,
        "total_processed": session["total_processed"],
        "rankings": session["rankings"],
    }


@app.post("/api/jd/parse")
async def parse_job_description(file: UploadFile = File(...)):
    """
    Parses a Job Description .docx file and returns:
    - parsed_jd: structured JSON with all extracted fields
    - evaluation_text: a condensed, noise-free string ready for the /api/rank/evaluate endpoint
    """
    if not file.filename.endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files are supported.")
        
    temp_file_path = ""
    try:
        import tempfile
        import json
        
        # Save uploaded file to a temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name

        # Run the full parser pipeline
        json_result = run_pipeline(temp_file_path)
        
        # Clean up temp file immediately
        os.unlink(temp_file_path)
        
        # Build structured model and derive the evaluation text
        parsed_dict = json.loads(json_result)
        jd_model = JobDescriptionInput(**parsed_dict)
        
        return {
            "parsed_jd": parsed_dict,
            "evaluation_text": jd_model.to_evaluation_text()
        }
        
    except Exception as exc:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        raise HTTPException(status_code=500, detail=f"Failed to parse JD: {str(exc)}")


@app.post("/api/rank/export")
async def export_stateless_rankings(
    rankings: List[dict] = Body(...)
):
    """
    Stateless Export Endpoint: Accepts the current sorted candidate 
    rankings state directly from the client and converts it into a 
    downloadable CSV file stream. Top 100 candidates are ranked; 
    the rest are marked as rejected. Columns: candidate_id, rank, score, ai_reasoning.
    """
    if not rankings:
        raise HTTPException(status_code=400, detail="Rankings data matrix payload cannot be empty.")
        
    try:
        csv_stream = convert_rankings_to_csv_stream(rankings)
        
        return StreamingResponse(
            csv_stream,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=AI_Recruiter_Leaderboard_Export.csv"}
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate CSV export stream: {str(exc)}"
        )

if __name__ == "__main__":
    import uvicorn 
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)