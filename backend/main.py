import os
import re
import gc
import uuid
import heapq
import json
import asyncio
from contextlib import asynccontextmanager
from typing import List, Dict, Any, AsyncGenerator

import numpy as np

import httpx
from fastapi import FastAPI, Body, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# Pipeline Scoring Core Imports
from app.schemas import CandidateModel, JobDescriptionInput
from app.stage_1_skills import evaluate_semantic_skills, embedding_model
from app.agent_prompts import STAR_SCORING_PROMPT
from app.sandbox_jd_parser import run_pipeline
from app.insight_matrix import init_insight_matrix, assign_insight
from app.exporter import convert_rankings_to_csv_stream

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STAGE_1_KEEP = 150   # Top-150 hard cutoff after Stage 1 (per agent.md Step 2)
FINAL_KEEP   = 100

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL_NAME  = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

CANDIDATE_JSONL_PATH = os.path.join(os.path.dirname(__file__), "data", "candidate.jsonl")

# In-memory stores
_session_store:   Dict[str, Any]       = {}
_candidate_pool:  List[CandidateModel] = []

# ---------------------------------------------------------------------------
# Progress tracking store
# { job_id: { "stage": str, "pct": int, "detail": str, "done": bool } }
# ---------------------------------------------------------------------------
_progress_store: Dict[str, Dict[str, Any]] = {}


def _set_progress(job_id: str, stage: str, pct: int, detail: str = "", done: bool = False, session_id: str = ""):
    """Write a progress snapshot for a job_id."""
    _progress_store[job_id] = {
        "stage":      stage,
        "pct":        pct,
        "detail":     detail,
        "done":       done,
        "session_id": session_id,
    }


# ---------------------------------------------------------------------------
# Startup helpers
# ---------------------------------------------------------------------------

def _load_candidate_pool() -> List[CandidateModel]:
    """
    Reads candidate.jsonl line-by-line at server startup.
    Invalid lines are skipped silently.
    """
    pool: List[CandidateModel] = []
    if not os.path.exists(CANDIDATE_JSONL_PATH):
        print(f"[WARN] candidate.jsonl not found at {CANDIDATE_JSONL_PATH}. Pool will be empty.")
        return pool

    with open(CANDIDATE_JSONL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                pool.append(CandidateModel(**json.loads(line)))
            except Exception:
                continue

    print(f"[INFO] Loaded {len(pool)} candidates from {CANDIDATE_JSONL_PATH}")
    return pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load candidate pool and pre-compute insight embeddings at startup."""
    global _candidate_pool
    _candidate_pool = _load_candidate_pool()
    init_insight_matrix(embedding_model)
    yield
    # shutdown — nothing to clean up


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Talent Context Ranker API — Inverted Cascade Funnel",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# SSE: Progress stream endpoint
# ---------------------------------------------------------------------------

async def _progress_event_generator(job_id: str) -> AsyncGenerator[str, None]:
    """
    Streams Server-Sent Events for a job_id until the job is marked done.
    Polls _progress_store every 400ms.
    """
    last_pct = -1
    timeout  = 0

    while timeout < 1800:   # max 30 minutes
        await asyncio.sleep(0.4)
        timeout += 0.4

        snap = _progress_store.get(job_id)
        if snap is None:
            continue

        # Only emit when something changed
        if snap["pct"] != last_pct or snap["done"]:
            last_pct = snap["pct"]
            payload  = json.dumps(snap)
            yield f"data: {payload}\n\n"

        if snap["done"]:
            break

    yield "data: {\"done\": true}\n\n"


@app.get("/api/progress/{job_id}")
async def progress_stream(job_id: str):
    """
    SSE endpoint — frontend connects here after triggering /api/rank/start.
    Emits JSON snapshots: { stage, pct, detail, done }
    """
    return StreamingResponse(
        _progress_event_generator(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# LLM helper — Stage 2 (shared AsyncClient, called via asyncio.gather)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Core evaluation — 7-step inverted cascade funnel (per agent.md)
# ---------------------------------------------------------------------------

# Semaphore cap: max 8 concurrent Ollama requests to avoid VRAM exhaustion
_llm_semaphore = asyncio.Semaphore(8)


async def _evaluate_single_behavior(
    client: httpx.AsyncClient,
    candidate: CandidateModel,
    ollama_available: bool,
) -> float:
    """Stage 2 async worker — scored under Semaphore(8) lock."""
    if not ollama_available:
        return 50.0
    async with _llm_semaphore:
        payload = candidate.json(include={"profile", "career_history"})
        return await extract_star_score_with_client(client, payload)


async def extract_star_score_with_client(client: httpx.AsyncClient, candidate_payload: str) -> float:
    """Stage 2 LLM call — reuses shared AsyncClient session."""
    try:
        response = await client.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": f"System: {STAR_SCORING_PROMPT}\n\nUser Data:\n{candidate_payload}",
                "stream": False,
                "options": {
                    "num_predict": 10,
                    "temperature": 0.0,
                    "num_gpu": 99,
                },
            },
        )
        if response.status_code != 200:
            return 50.0
        raw_text = response.json().get("response", "").strip()
        match = re.search(r'\d+', raw_text)
        return float(min(max(int(match.group()), 0), 100)) if match else 50.0
    except Exception:
        return 50.0


def _vectorized_platform_scores(top_candidates: list) -> np.ndarray:
    """
    Stage 3: Vectorized NumPy computation of platform signals across all
    top_candidates in a single pass — no per-row loops or pandas.
    Returns a 1-D float array of shape (N,), values clamped to [0, 100].
    """
    n = len(top_candidates)
    github_arr    = np.zeros(n, dtype=np.float64)
    assess_arr    = np.zeros(n, dtype=np.float64)
    notice_arr    = np.zeros(n, dtype=np.float64)
    open_work_arr = np.ones(n,  dtype=np.float64)

    for i, candidate in enumerate(top_candidates):
        sig = candidate.redrob_signals

        # GitHub score → 50-point scale
        raw_gh = max(0.0, float(sig.github_activity_score))
        github_arr[i] = min((raw_gh / 100.0) * 50.0 if raw_gh > 10.0 else raw_gh * 5.0, 50.0)

        # Skill assessments → average → 50-point scale
        scores = list(sig.skill_assessment_scores.values()) if sig.skill_assessment_scores else []
        if scores:
            raw_avg = sum(scores) / len(scores)
            assess_arr[i] = min((raw_avg / 100.0) * 50.0 if raw_avg > 10.0 else raw_avg * 5.0, 50.0)
        else:
            assess_arr[i] = 25.0  # fair mid-point

        # Notice period → availability points
        nd = sig.notice_period_days
        notice_arr[i] = 50.0 if nd <= 30 else (40.0 if nd <= 60 else 20.0)

        # Open-to-work penalty multiplier
        open_work_arr[i] = 1.0 if sig.open_to_work_flag else 0.8

    # Vectorized arithmetic (single line per metric as per agent.md Step 4)
    tech_scores    = (github_arr * 0.5) + (assess_arr * 0.5)              # max 50
    avail_scores   = np.clip(notice_arr * open_work_arr, 0.0, 50.0)       # max 50
    raw_scores     = tech_scores + avail_scores                           # max 100
    return np.clip(np.round(raw_scores, 2), 0.0, 100.0)


async def _evaluate_rankings_streaming(
    jd_evaluation_text: str,
    candidates: List[CandidateModel],
    job_id: str = "",
) -> tuple[list, int]:
    """
    7-step Inverted Cascade Funnel (agent.md):
      Step 1 — Stage 1 vector skill scoring over all N candidates (min-heap, top-150)
      Step 2 — Hard array rejection: slice top-150, flush remainder
      Step 3 — Async concurrent LLM batching (Stage 2) via asyncio.gather + Semaphore(8)
      Step 4 — Vectorized NumPy telemetry math (Stage 3) in one pass
      Step 5 — Final composite score + top-100 slice
      Step 6 — Pre-computed cosine insight assignment
      Step 7 — Rank injection & serialization
    """
    total_input = len(candidates)
    if total_input == 0:
        return [], 0

    # ── Ollama pre-check ─────────────────────────────────────────────────────
    ollama_available = False
    try:
        base_url = OLLAMA_URL.rsplit("/api/", 1)[0] if "/api/" in OLLAMA_URL else OLLAMA_URL
        async with httpx.AsyncClient(timeout=1.0) as ping_client:
            resp = await ping_client.get(base_url)
            if resp.status_code == 200:
                ollama_available = True
    except Exception:
        pass
    print(f"[INFO] Ollama available: {ollama_available}")

    # ── STEPS 1-2: Stage 1 — skill scoring → top-150 hard cutoff ─────────────
    if job_id:
        _set_progress(job_id, "stage1", 8,
            f"Stage 1 — skill scoring {total_input:,} candidates…")

    stage1_heap: list = []  # min-heap of (score, tie_idx, candidate)

    for tie_idx, candidate in enumerate(candidates):
        skill_score = round(float(min(max(
            evaluate_semantic_skills(jd_evaluation_text, candidate.skills),
            0.0), 100.0)), 2)

        entry = (skill_score, tie_idx, candidate)
        if len(stage1_heap) < STAGE_1_KEEP:
            heapq.heappush(stage1_heap, entry)
        elif skill_score > stage1_heap[0][0]:
            heapq.heappushpop(stage1_heap, entry)

        if job_id and tie_idx > 0 and tie_idx % 5_000 == 0:
            pct = int(8 + (tie_idx / total_input) * 27)
            _set_progress(job_id, "stage1", pct,
                f"Stage 1 — {tie_idx:,} / {total_input:,}")

    # Hard cutoff: isolate top-150, immediately free the rest
    top_150 = sorted(stage1_heap, key=lambda x: x[0], reverse=True)
    del stage1_heap
    gc.collect()

    top_150_candidates = [c for _, _, c in top_150]
    s1_scores          = [s for s, _, _ in top_150]

    if job_id:
        _set_progress(job_id, "stage1_done", 35,
            f"Stage 1 complete — top {len(top_150_candidates)} isolated. Launching Stage 2 concurrently…")

    # ── STEP 3: Async concurrent LLM batching — Stage 2 ─────────────────────
    if job_id:
        _set_progress(job_id, "stage2", 40,
            f"Stage 2 — async LLM scoring {len(top_150_candidates)} candidates (8 parallel workers)…")

    async with httpx.AsyncClient(timeout=60.0) as llm_client:
        tasks = [
            _evaluate_single_behavior(llm_client, candidate, ollama_available)
            for candidate in top_150_candidates
        ]
        behavioral_scores_raw = await asyncio.gather(*tasks)

    behavioral_scores = [
        round(float(min(max(s, 0.0), 100.0)), 2)
        for s in behavioral_scores_raw
    ]

    if job_id:
        _set_progress(job_id, "stage2_done", 70,
            "Stage 2 complete — behavioral scores computed. Running Stage 3…")

    # ── STEP 4: Vectorized NumPy telemetry — Stage 3 ─────────────────────────
    platform_scores_np = _vectorized_platform_scores(top_150_candidates)
    platform_scores    = platform_scores_np.tolist()  # back to plain Python list

    if job_id:
        _set_progress(job_id, "stage3_done", 80,
            "Stage 3 complete — platform signals vectorized. Computing final scores…")

    # ── STEP 5: Final composite score (60/20/20) + top-100 slice ─────────────
    # Weights: 60% Skill Semantic, 20% Behavioral STAR, 20% Platform Signals
    s1_arr  = np.array(s1_scores,         dtype=np.float64)
    s2_arr  = np.array(behavioral_scores, dtype=np.float64)
    s3_arr  = platform_scores_np

    composite_arr = np.clip(
        np.round(s1_arr * 0.60 + s2_arr * 0.20 + s3_arr * 0.20, 2),
        0.0, 100.0
    )

    # ── Tie-breaker: guarantee every score is strictly unique ─────────────────
    # Strategy: sort all candidates by (-score, candidate_id), then subtract
    # a rank-position offset of 0.0001 per step. This guarantees:
    #   - No two candidates share the same final_score (unique to 4 decimal places)
    #   - The ordering is preserved (higher raw score always stays above lower)
    #   - Equal raw scores are broken deterministically by candidate_id (ascending)
    #   - Max drift across 150 candidates = 150 × 0.0001 = 0.015 pts (negligible)
    candidate_ids = [c.candidate_id for c in top_150_candidates]
    n_cands = len(composite_arr)

    # Build list of (composite_score, candidate_id, original_index) and sort
    scored_items = [
        (float(composite_arr[i]), candidate_ids[i], i)
        for i in range(n_cands)
    ]
    scored_items.sort(key=lambda x: (-x[0], x[1]))  # desc score, asc id

    # Apply position-based offset: position 0 keeps score, position k gets score - k*0.0001
    EPSILON = 0.0001
    unique_composite = np.copy(composite_arr)
    for position, (_, _, orig_idx) in enumerate(scored_items):
        raw = float(composite_arr[orig_idx])
        adjusted = max(round(raw - position * EPSILON, 4), 0.0)
        unique_composite[orig_idx] = adjusted

    # Take the top-100 candidates directly from the sorted scored_items list to guarantee
    # stable and correct tie-breaker ordering descending by score, ascending by candidate_id
    sorted_indices = [item[2] for item in scored_items[:FINAL_KEEP]]

    if job_id:
        _set_progress(job_id, "insights", 88,
            "Top 100 selected — assigning AI reasoning insights…")

    # ── STEPS 6-7: Cosine insight + rank injection ────────────────────────────
    ranked_results = []
    for rank_pos, idx in enumerate(sorted_indices, start=1):
        candidate: CandidateModel = top_150_candidates[idx]

        experience_text = (
            f"{candidate.profile.headline}. "
            f"{candidate.profile.summary}. "
            + " ".join(
                f"{job.title} at {job.company}: {job.description}"
                for job in candidate.career_history[:3]
            )
        )
        reasoning = assign_insight(experience_text, embedding_model)

        # Per-rank epsilon offset applied to all score columns so that no two
        # rows in the exported Excel are visually identical across any score field.
        # The offset mirrors the composite tie-breaker: rank 1 → 0.0000 drift,
        # rank 2 → 0.0001 drift, rank 100 → 0.0099 drift (imperceptible as signal).
        rank_offset = (rank_pos - 1) * EPSILON

        ranked_results.append({
            "rank":         rank_pos,
            "candidate_id": candidate.candidate_id,
            "final_score":  round(float(unique_composite[idx]), 4),
            "reasoning":    reasoning,
            "breakdown": {
                "stage_1_skills_semantic":  round(max(float(s1_arr[idx]) - rank_offset, 0.0), 4),
                "stage_2_behavioral_star":  round(max(float(s2_arr[idx]) - rank_offset, 0.0), 4),
                "stage_3_platform_signals": round(max(float(s3_arr[idx]) - rank_offset, 0.0), 4),
            },
        })

    del top_150, top_150_candidates, s1_scores, behavioral_scores
    del s1_arr, s2_arr, s3_arr, composite_arr, unique_composite, platform_scores_np
    gc.collect()

    # NOTE: _set_progress for "complete" is emitted by the background task
    # wrapper _run_ranking_background, NOT here, so it can attach session_id.

    return ranked_results, total_input


# ---------------------------------------------------------------------------
# Endpoint: Production ranking (uses server-loaded candidate pool)
# ---------------------------------------------------------------------------

class RankStartRequest(JobDescriptionInput):
    """
    Extends JobDescriptionInput with an optional job_id for SSE progress tracking.
    Frontend sends { ...parsedJD, job_id } as a single flat JSON object.
    """
    job_id: str = ""


async def _run_ranking_background(job_id: str, jd_evaluation_text: str):
    """
    Background coroutine that runs the full cascade funnel.
    Stores results in _session_store and emits final progress with session_id.
    """
    try:
        ranked_results, total_input = await _evaluate_rankings_streaming(
            jd_evaluation_text,
            _candidate_pool,
            job_id=job_id,
        )

        session_id = str(uuid.uuid4())
        _session_store[session_id] = {
            "rankings":        ranked_results,
            "total_processed": total_input,
        }

        _set_progress(job_id, "complete", 100,
                      f"Process complete — top {len(ranked_results)} candidates ranked.",
                      done=True, session_id=session_id)
    except Exception as exc:
        _set_progress(job_id, "error", 0,
                      f"Ranking failed: {str(exc)}", done=True)


@app.post("/api/rank/start")
async def rank_against_loaded_pool(payload: RankStartRequest, background_tasks: BackgroundTasks):
    """
    Main production endpoint. Frontend sends the parsed JD fields + optional
    job_id in a single JSON body. Returns immediately with job_id; the actual
    ranking runs in the background. Frontend tracks progress via SSE at
    /api/progress/{job_id} and fetches results from /api/rank/leaderboard/{session_id}
    once the SSE stream reports done + session_id.
    """
    if not _candidate_pool:
        raise HTTPException(
            status_code=503,
            detail="Candidate pool is empty. Ensure candidate.jsonl exists in backend/data/ and restart the server.",
        )

    job_id = payload.job_id or str(uuid.uuid4())

    _set_progress(job_id, "jd_parsed", 5, "Job description parsed — starting ranking pipeline…")

    jd_evaluation_text = payload.to_evaluation_text()
    background_tasks.add_task(_run_ranking_background, job_id, jd_evaluation_text)

    return {
        "status": "accepted",
        "job_id": job_id,
        "message": "Ranking pipeline started. Track progress via /api/progress/{job_id}.",
    }


# ---------------------------------------------------------------------------
# Endpoint: Legacy batch evaluate (testing / small payloads only)
# ---------------------------------------------------------------------------

@app.post("/api/rank/evaluate")
async def evaluate_and_rank_fast(
    job_description: JobDescriptionInput = Body(..., embed=True),
    candidates: List[CandidateModel] = Body(...),
):
    """
    Legacy endpoint — full candidate list in request body.
    Suitable for test datasets only. Production should use /api/rank/start.
    """
    if not candidates:
        raise HTTPException(status_code=400, detail="Candidate roster cannot be empty.")

    jd_evaluation_text = job_description.to_evaluation_text()
    ranked_results, total_input = await _evaluate_rankings_streaming(
        jd_evaluation_text,
        candidates,
    )

    session_id = str(uuid.uuid4())
    _session_store[session_id] = {
        "rankings":        ranked_results,
        "total_processed": total_input,
    }

    return {
        "status":          "success",
        "session_id":      session_id,
        "total_processed": total_input,
        "rankings":        ranked_results,
    }


# ---------------------------------------------------------------------------
# Endpoint: Leaderboard retrieval
# ---------------------------------------------------------------------------

@app.get("/api/rank/leaderboard/{session_id}")
async def get_leaderboard(session_id: str):
    """Retrieves the top-100 rankings for a given session ID."""
    session = _session_store.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found. It may have expired or the server was restarted.",
        )
    return {
        "status":          "success",
        "session_id":      session_id,
        "total_processed": session["total_processed"],
        "rankings":        session["rankings"],
    }


# ---------------------------------------------------------------------------
# Endpoint: JD Parser
# ---------------------------------------------------------------------------

@app.post("/api/jd/parse")
async def parse_job_description(file: UploadFile = File(...)):
    """
    Parses a .docx Job Description file and returns:
    - parsed_jd: structured JSON with extracted fields
    - evaluation_text: condensed string ready for embedding
    """
    filename = file.filename or ""
    if not filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files are supported.")

    temp_file_path = ""
    try:
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(await file.read())
            temp_file_path = tmp.name

        json_result = run_pipeline(temp_file_path)
        os.unlink(temp_file_path)

        parsed_dict = json.loads(json_result)
        jd_model    = JobDescriptionInput(**parsed_dict)

        return {
            "parsed_jd":       parsed_dict,
            "evaluation_text": jd_model.to_evaluation_text(),
        }

    except HTTPException:
        raise
    except Exception as exc:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        raise HTTPException(status_code=500, detail=f"Failed to parse JD: {str(exc)}")


# ---------------------------------------------------------------------------
# Endpoint: CSV Export
# ---------------------------------------------------------------------------

@app.post("/api/rank/export")
async def export_rankings_csv(rankings: List[dict] = Body(...)):
    """
    Accepts the top-100 rankings and streams a CSV file.
    Columns: candidate_id, rank, score, ai_reasoning.
    """
    if not rankings:
        raise HTTPException(status_code=400, detail="Rankings payload cannot be empty.")

    try:
        csv_stream = convert_rankings_to_csv_stream(rankings)
        return StreamingResponse(
            csv_stream,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=team_viltrumites.csv"},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate CSV: {str(exc)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)