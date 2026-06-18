import json
import time
import requests
import os

# Configuration
API_BASE_URL = "http://localhost:8000/api/rank"
CANDIDATE_FILE_PATH = os.path.join("data", "candidate.json")
JOB_DESCRIPTION = "Looking for a strong Backend Engineer with experience in Python, API design, and Data processing."

def main():
    print("🚀 Starting End-to-End Performance Test...\n")
    total_start_time = time.time()

    # 1. Load data
    try:
        with open(CANDIDATE_FILE_PATH, "r", encoding="utf-8") as f:
            candidates_data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load candidate data: {e}")
        return

    print(f"✅ Loaded {len(candidates_data)} candidates from {CANDIDATE_FILE_PATH}")

    # 2. Pass JSON data to backend & Calculate Scores & Store in DB
    print("\n⏳ Sending POST request to /api/rank/evaluate ...")
    evaluate_start_time = time.time()
    
    payload = {
        "job_description": JOB_DESCRIPTION,
        "candidates": candidates_data
    }
    
    try:
        evaluate_resp = requests.post(f"{API_BASE_URL}/evaluate", json=payload)
        evaluate_resp.raise_for_status()
        evaluate_data = evaluate_resp.json()
    except Exception as e:
        print(f"❌ Evaluation request failed: {e}")
        if 'evaluate_resp' in locals() and evaluate_resp:
            print(f"Response: {evaluate_resp.text}")
        return

    evaluate_end_time = time.time()
    session_id = evaluate_data.get("session_id")
    print(f"✅ Successfully evaluated and stored. Session ID: {session_id}")
    print(f"⏱️ Time taken for evaluation & DB storage: {evaluate_end_time - evaluate_start_time:.2f} seconds")

    # 3. Fetch from DB (Simulating Frontend Dashboard Load)
    print(f"\n⏳ Fetching leaderboard data for dashboard (GET /api/rank/leaderboard/{session_id})...")
    fetch_start_time = time.time()

    try:
        fetch_resp = requests.get(f"{API_BASE_URL}/leaderboard/{session_id}")
        fetch_resp.raise_for_status()
        leaderboard_data = fetch_resp.json()
    except Exception as e:
        print(f"❌ Fetch request failed: {e}")
        return

    fetch_end_time = time.time()
    print(f"✅ Successfully fetched leaderboard data for {len(leaderboard_data.get('rankings', []))} candidates.")
    print(f"⏱️ Time taken to fetch dashboard data: {fetch_end_time - fetch_start_time:.2f} seconds")

    # Final Total Calculation
    total_end_time = time.time()
    total_time = total_end_time - total_start_time
    
    print("\n" + "="*50)
    print("📊 PERFORMANCE REPORT")
    print("="*50)
    print(f"1. Processing, Scoring & DB Write: {evaluate_end_time - evaluate_start_time:.2f}s")
    print(f"2. DB Read & Dashboard Fetch:      {fetch_end_time - fetch_start_time:.2f}s")
    print("-" * 50)
    print(f"🏆 Total End-to-End Time:          {total_time:.2f}s")
    print("="*50)

if __name__ == "__main__":
    main()
