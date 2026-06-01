"""Verify sidecar *_scrubbed.csv files match the t.co scrub contract.

Run from repo root:

    PYTHONPATH=. uv run python scripts/verify_twitter_tco_scrub.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from data_platform.preprocessing.validators.twitter_validators import (
    has_tco_links,
    strip_tco_links,
)

_DATA_ROOT = Path(__file__).resolve().parents[1] / "data_platform" / "data"
TWITTER_ROOT = _DATA_ROOT / "twitter"


def verify_twitter_tco_scrub(*, twitter_root: Path) -> None:
    verified = 0

    for original_path in sorted(twitter_root.rglob("*.csv")):
        if original_path.name.endswith("_scrubbed.csv"):
            continue

        scrubbed_path = original_path.with_name(
            f"{original_path.stem}_scrubbed{original_path.suffix}"
        )

        orig_df = pd.read_csv(original_path)
        has_text = "text" in orig_df.columns
        orig_has_tco = (
            has_text and orig_df["text"].astype(str).map(has_tco_links).any()
        )

        if not scrubbed_path.exists():
            if orig_has_tco:
                print(f"FAIL missing sidecar: {original_path}")
                sys.exit(1)
            continue

        if not has_text:
            print(f"FAIL scrubbed exists but original lacks text column: {original_path}")
            sys.exit(1)

        scr_df = pd.read_csv(scrubbed_path)

        if "text" not in scr_df.columns:
            print(f"FAIL scrubbed file lacks text column: {scrubbed_path}")
            sys.exit(1)

        if not orig_has_tco:
            print(f"FAIL original has no t.co links: {original_path}")
            sys.exit(1)

        if scr_df["text"].astype(str).map(has_tco_links).any():
            print(f"FAIL scrubbed still has t.co links: {scrubbed_path}")
            sys.exit(1)

        if len(scr_df) != len(orig_df):
            print(
                f"FAIL row count mismatch: {original_path} "
                f"({len(orig_df)} vs {len(scr_df)})"
            )
            sys.exit(1)

        expected_text = orig_df["text"].astype(str).map(strip_tco_links).tolist()
        if scr_df["text"].tolist() != expected_text:
            print(f"FAIL text mismatch: {scrubbed_path}")
            sys.exit(1)

        if not orig_df.drop(columns=["text"]).equals(scr_df.drop(columns=["text"])):
            print(f"FAIL non-text columns differ: {scrubbed_path}")
            sys.exit(1)

        print(f"PASS {original_path.name} -> {scrubbed_path.name}")
        verified += 1

    print(f"verified {verified} pair(s)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify sidecar *_scrubbed.csv files for Twitter data",
    )
    parser.add_argument(
        "--twitter-root",
        type=Path,
        default=TWITTER_ROOT,
        help="Root directory for Twitter CSV data",
    )
    args = parser.parse_args()
    verify_twitter_tco_scrub(twitter_root=args.twitter_root)


if __name__ == "__main__":
    main()
