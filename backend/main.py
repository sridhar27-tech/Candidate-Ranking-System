import os
import uuid
import datetime
import asyncio
from typing import List
import httpx
from fastapi import FastAPI, Body, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Pipeline Scoring Core Imports
from app.schemas import CandidateModel
from app.stage_1_skills import evaluate_semantic_skills
from app.stage_2_behavioral import evaluate_behavioral_star
from app.stage_3_signals import calculate_platform_signals 

# Database Configuration and Pydantic Schema Layers
from app.db import get_leaderboard_collection
from app.models import LeaderboardSessionDocument
from app.agent_prompts import SCREENER_SYSTEM_PROMPT, BEHAVIORAL_SYSTEM_PROMPT, CRITIC_SYSTEM_PROMPT

app = FastAPI(title="Talent Context Ranker API (Multi-Agent MongoDB Engine)")

# Enable unrestricted development CORS policy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration for Local Ollama Inference (VRAM-Optimized Environment)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")


async def call_local_agent(system_prompt: str, user_payload: str) -> str:
    """
    Dispatches asynchronous network requests to the local Ollama instance.
    Keeps prompts brief to ensure total VRAM footings remain comfortably within 6GB.
    """
    combined_prompt = f"System: {system_prompt}\n\nUser Content: {user_payload}"
    
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "prompt": combined_prompt,
                    "stream": False
                }
            )
            if response.status_code != 200:
                error_detail = response.text
                raise HTTPException(
                    status_code=500, 
                    detail=f"Ollama execution error status: {response.status_code}. Detail: {error_detail}"
                )
            
            result_json = response.json()
            return result_json.get("response", "").strip()
            
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503, 
            detail=f"Connection failure to local Ollama runtime port: {exc}"
        )


async def _execute_and_serialize_pipeline(job_description: str, candidates: List[CandidateModel]) -> List[dict]:
    """
    Executes the multi-agent pipeline: Runs Tech Screener and Behavioral Assessor 
    CONCURRENTLY via asyncio.gather to save local GPU overhead, then hands 
    both insights sequentially to the Editorial Critic for compilation.
    """
    results = []
    for candidate in candidates:
        # Phase 1: Native C++ Core Module (Fast semantic parsing)
        semantic_score = evaluate_semantic_skills(job_description, candidate.skills)
        
        # Phase 3: Platform Telemetry Signal Evaluation
        platform_score = calculate_platform_signals(candidate.redrob_signals)
        
        # -----------------------------------------------------------------
        # PHASE 2: LIGHTWEIGHT ASYNC MULTI-AGENT ORCHESTRATION LAYER
        # -----------------------------------------------------------------
        
        # Construct highly targeted payloads to preserve LLM input tokens
        tech_payload = f"Target JD:\n{job_description}\n\nCandidate Skills: {candidate.skills}\nProfile Summary: {candidate.profile}"
        behavioral_payload = f"Target JD:\n{job_description}\n\nCareer History:\n{candidate.career_history}\nProfile Summary: {candidate.profile}"
        
        # Fire Agent A and Agent B simultaneously to save hardware network cycle delay times
        agent_a_task = call_local_agent(SCREENER_SYSTEM_PROMPT, tech_payload)
        agent_b_task = call_local_agent(BEHAVIORAL_SYSTEM_PROMPT, behavioral_payload)
        
        # Extract notes out of the concurrent task resolution pool
        screener_notes, assessor_notes = await asyncio.gather(agent_a_task, agent_b_task)
        
        # Group independent insights together for Agent C (The Critic)
        critic_payload = (
            f"Target JD:\n{job_description}\n\n"
            f"--- Tech Screener Diagnostics ---\n{screener_notes}\n\n"
            f"--- Behavioral Assessor Diagnostics ---\n{assessor_notes}"
        )
        
        # Run the Editorial Critic agent sequentially to forge the final compiled result
        ai_reasoning_paragraph = await call_local_agent(CRITIC_SYSTEM_PROMPT, critic_payload)
        
        # Retain original operational metrics calculation for the behavioral alignment rating
        behavioral_score, _ = evaluate_behavioral_star(job_description, candidate.profile, candidate.career_history)
        
        # Comprehensive Aggregated Weight Matrix Logic Calculation:
        # 40% Matrix Skills Match + 40% STAR Contextual Alignment + 20% Intent/Availability Signals
        composite_score = (semantic_score * 0.40) + (behavioral_score * 0.40) + (platform_score * 0.20)
        
        results.append({
            "candidate_id": candidate.candidate_id,
            "final_score": round(composite_score, 2),
            "breakdown": {
                "stage_1_skills_semantic": round(semantic_score, 2),
                "stage_2_behavioral_star": round(behavioral_score, 2),
                "stage_3_platform_signals": round(platform_score, 2)
            },
            # This is your high-impact 7-8 line structured paragraph compiled by the Critic Agent
            "ai_justification": ai_reasoning_paragraph
        })
        
    # Order rankings directly by best score prior to returning
    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results


@app.post("/api/rank/evaluate")
async def evaluate_candidates(
    job_description: str = Body(..., embed=True),
    candidates: List[CandidateModel] = Body(...),
    collection = Depends(get_leaderboard_collection)
):
    """
    Triggers multi-agent evaluation pipeline operations, saves results 
    to MongoDB collections, and yields a secure, unguessable tracking UUID slug.
    """
    session_id = str(uuid.uuid4())
    
    # Run evaluation matrix pipeline across array elements
    processed_rankings = await _execute_and_serialize_pipeline(job_description, candidates)
    
    # Map the verified Pydantic schema document state block
    session_doc = LeaderboardSessionDocument(
        session_id=session_id,
        total_processed=len(processed_rankings),
        rankings=processed_rankings
    )
    
    # Save directly to MongoDB in one quick, structural async database commit
    await collection.insert_one(session_doc.dict())
    
    return {
        "status": "success",
        "session_id": session_id,
        "total_processed": len(processed_rankings),
        "rankings": processed_rankings
    }


@app.get("/api/rank/leaderboard/{session_id}")
async def get_stored_leaderboard(
    session_id: str, 
    collection = Depends(get_leaderboard_collection)
):
    """
    Optimized Summary Endpoint: Fetches candidate profiles while completely 
    excluding the heavy text paragraph, preventing any network or dashboard lag.
    """
    # MongoDB Projection Optimization: "rankings.ai_justification": 0 prevents text from streaming
    document = await collection.find_one(
        {"session_id": session_id},
        projection={"_id": 0, "rankings.ai_justification": 0}
    )
    
    if not document:
        raise HTTPException(status_code=404, detail="Leaderboard execution signature not found.")
        
    return document


@app.get("/api/rank/leaderboard/{session_id}/candidate/{candidate_id}/justification")
async def get_candidate_justification(
    session_id: str,
    candidate_id: str,
    collection = Depends(get_leaderboard_collection)
):
    """
    Deep-Dive Detail Endpoint: Fetches and returns ONLY the 7-8 line text block for 
    a specific candidate when clicked by the recruiter.
    """
    # Uses MongoDB '$elemMatch' projection to extract just one target element out of the data array
    document = await collection.find_one(
        {"session_id": session_id, "rankings.candidate_id": candidate_id},
        projection={"_id": 0, "rankings.$": 1}
    )
    
    if not document or "rankings" not in document:
        raise HTTPException(status_code=404, detail="Candidate or Session matching signature not found.")
        
    target_candidate = document["rankings"][0]
    return {
        "candidate_id": candidate_id,
        "ai_justification": target_candidate.get("ai_justification", "No justification recorded.")
    }


if __name__ == "__main__":
    import uvicorn 
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)