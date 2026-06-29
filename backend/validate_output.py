"""
Quick local validation — mirrors validate_submission.py from the challenge.
Run from the backend/ directory:

    python validate_output.py <path_to_output.csv>

Exits 0 on success, 1 on any failure.
"""
import sys
import subprocess
from pathlib import Path

VALIDATOR = Path(__file__).parent.parent / (
    "dataset/[PUB] India_runs_data_and_ai_challenge/"
    "India_runs_data_and_ai_challenge/validate_submission.py"
)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_output.py <output.csv>")
        sys.exit(1)

    csv_path = sys.argv[1]

    if not VALIDATOR.exists():
        print(f"[WARN] Validator not found at {VALIDATOR}. Running basic checks only.")
        # Basic checks inline
        import csv, re
        PATTERN = re.compile(r"^CAND_[0-9]{7}$")
        with open(csv_path, encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
        header = rows[0] if rows else []
        data   = [r for r in rows[1:] if any(c.strip() for c in r)]
        errors = []
        if header != ["candidate_id", "rank", "score", "reasoning"]:
            errors.append(f"Bad header: {header}")
        if len(data) != 100:
            errors.append(f"Expected 100 rows, got {len(data)}")
        scores = []
        for i, row in enumerate(data, start=2):
            if len(row) != 4:
                errors.append(f"Row {i}: expected 4 columns, got {len(row)}")
                continue
            cid, rank_s, score_s, _ = row
            if not PATTERN.match(cid.strip()):
                errors.append(f"Row {i}: bad candidate_id '{cid}'")
            try:
                scores.append(float(score_s))
            except ValueError:
                errors.append(f"Row {i}: non-float score '{score_s}'")
        for j in range(len(scores) - 1):
            if scores[j] < scores[j+1]:
                errors.append(f"Scores not non-increasing at rows {j+2}/{j+3}: {scores[j]} < {scores[j+1]}")
        if errors:
            print(f"Validation FAILED ({len(errors)} issues):")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        print("Basic validation passed.")
        sys.exit(0)

    # Run the official validator
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), csv_path],
        capture_output=False,
    )
    sys.exit(result.returncode)
