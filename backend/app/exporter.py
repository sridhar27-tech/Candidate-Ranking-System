# app/exporter.py
# ---------------------------------------------------------------------------
# Generates the submission CSV that satisfies validate_submission.py rules:
#
#   - Header row: candidate_id,rank,score,reasoning  (exact, in this order)
#   - Exactly 100 data rows (rows 2–101)
#   - rank: integer 1–100, each used exactly once
#   - score: float, non-increasing by rank (with tie-breaker)
#   - Tie-break: when scores are equal, candidate_id ascending (lexicographic)
#   - UTF-8 encoding, no BOM
# ---------------------------------------------------------------------------
import io
import csv
import re

CANDIDATE_ID_PATTERN = re.compile(r"^CAND_[0-9]{7}$")
TOP_N = 100


def generate_submission_csv(rankings_list: list) -> io.BytesIO:
    """
    Takes a list of ranking dicts (from the pipeline or the session store),
    applies all submission constraints, and returns a UTF-8 CSV byte stream.

    Each dict must have at least:
        candidate_id  str
        final_score   float
        reasoning     str   (or ai_reasoning as legacy fallback)
        rank          int   (optional — will be re-assigned after sort)
    """

    # ── 1. Filter to valid candidate_id entries only ──────────────────────────
    valid = [
        r for r in rankings_list
        if CANDIDATE_ID_PATTERN.match(str(r.get("candidate_id", "")))
    ]

    # ── 2. Sort: descending score, then ascending candidate_id for tie-breaks ─
    valid.sort(
        key=lambda r: (-round(float(r.get("final_score", 0)), 10),
                       str(r.get("candidate_id", "")))
    )

    # ── 3. Slice exactly top-100 ──────────────────────────────────────────────
    top_100 = valid[:TOP_N]

    # ── 4. Write CSV ──────────────────────────────────────────────────────────
    text_buffer = io.StringIO()
    writer = csv.writer(text_buffer, lineterminator="\n")

    # Header — must match REQUIRED_HEADER in validate_submission.py exactly
    writer.writerow(["candidate_id", "rank", "score", "reasoning"])

    for rank_pos, record in enumerate(top_100, start=1):
        cid   = str(record.get("candidate_id", ""))
        score = float(record.get("final_score", 0))

        # Accept both key names produced by different pipeline versions
        reasoning = (
            record.get("reasoning")
            or record.get("ai_reasoning")
            or ""
        )

        writer.writerow([cid, rank_pos, score, reasoning])

    output = io.BytesIO()
    output.write(text_buffer.getvalue().encode("utf-8"))
    output.seek(0)
    return output


def convert_rankings_to_csv_stream(rankings_list: list) -> io.BytesIO:
    """Public interface used by the FastAPI export endpoint."""
    return generate_submission_csv(rankings_list)
