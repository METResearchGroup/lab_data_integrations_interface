"""Print toxicity_tier counts for a Reddit is_toxic_tiered feature CSV.

Run from repo root:

    uv run python scripts/how_many_toxic.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

INPUT_CSV = Path(
    "data_platform/data/reddit/reddit_d980a5af-d25f-4bf7-a3ea-1e312e40f67d/"
    "features/is_toxic_tiered.csv"
)


def main() -> None:
    df = pd.read_csv(INPUT_CSV)
    if "toxicity_tier" not in df.columns:
        raise KeyError(f"Missing `toxicity_tier` column in {INPUT_CSV}")

    counts = df["toxicity_tier"].value_counts()
    print(f"Input: {INPUT_CSV} ({len(df):,} rows)\n")
    print("toxicity_tier counts:")
    print(counts.to_string())


if __name__ == "__main__":
    main()
