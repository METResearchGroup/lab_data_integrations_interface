"""Sanity check: runs the upsampler via subprocess to generate a small batch of posts.

To run:
    PYTHONPATH=. uv run python collector/examples_test.py
"""

import subprocess
import sys
from pathlib import Path

EXAMPLES_PATH = Path(__file__).parent.parent / "experimentation" / "posts.csv"
TOTAL_SAMPLES = 100
N_PER_CALL = 5


def main() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "collector/upsampler.py",
            "--examples-path", str(EXAMPLES_PATH),
            "--total-samples", str(TOTAL_SAMPLES),
            "--n-per-call", str(N_PER_CALL),
        ],
        capture_output=False,
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
