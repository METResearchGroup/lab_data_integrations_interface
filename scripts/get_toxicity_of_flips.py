"""Score mirrored flip text with is_toxic_tiered and write labeled CSV.

Run from repo root:

    PYTHONPATH=. uv run python scripts/get_toxicity_of_flips.py
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from data_platform.generate_features.is_toxic_tiered.generate_feature import (
    generate_feature,
)

INPUT_CSV = Path(
    "/Users/mark/Documents/work/mirrorView-task/experiments/"
    "scaled_mirrors_generation_2026_06_02/generated_flips/"
    "2026_06_12-12:44:13/high_toxic.csv"
)
OUTPUT_CSV = INPUT_CSV.parent / "high_toxic_flips_with_labels_on_mirrored_text.csv"

TOXICITY_TIER_TO_SAMPLE_TYPE = {
    "low": "sample_low_toxicity",
    "medium": "sample_middle_toxicity",
    "high": "sample_high_toxicity",
}

MAX_WORKERS = 8


def _score_mirrored_text(uri: str, text: str) -> str:
    result = generate_feature(uri, text)
    return TOXICITY_TIER_TO_SAMPLE_TYPE[result.toxicity_tier]


def main() -> None:
    df = pd.read_csv(INPUT_CSV)
    if "mirrored_text" not in df.columns:
        raise KeyError(f"Missing `mirrored_text` column in {INPUT_CSV}")
    if "post_primary_key" not in df.columns:
        raise KeyError(f"Missing `post_primary_key` column in {INPUT_CSV}")

    rows = df.to_dict(orient="records")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        labels = list(
            executor.map(
                lambda row: _score_mirrored_text(
                    str(row["post_primary_key"]),
                    str(row["mirrored_text"]),
                ),
                rows,
            )
        )

    out = df.copy()
    out["mirrored_text_toxicity_type"] = labels
    out.to_csv(OUTPUT_CSV, index=False)

    print(f"Input:  {INPUT_CSV} ({len(df):,} rows)")
    print(f"Output: {OUTPUT_CSV}")
    print("\nmirrored_text_toxicity_type value counts:")
    print(out["mirrored_text_toxicity_type"].value_counts())


if __name__ == "__main__":
    main()
