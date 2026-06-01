"""One-off: write sidecar *_scrubbed.csv files with t.co links removed from text.

Run from repo root:

    PYTHONPATH=. uv run python scripts/scrub_twitter_tco_links.py --dry-run
    PYTHONPATH=. uv run python scripts/scrub_twitter_tco_links.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from data_platform.preprocessing.validators.twitter_validators import (
    has_tco_links,
    strip_tco_links,
)

_DATA_ROOT = Path(__file__).resolve().parents[1] / "data_platform" / "data"
TWITTER_ROOT = _DATA_ROOT / "twitter"


def scrub_twitter_tco_links(*, dry_run: bool, twitter_root: Path) -> None:
    scanned = 0
    scrubbed = 0
    skipped = 0

    for path in sorted(twitter_root.rglob("*.csv")):
        if path.name.endswith("_scrubbed.csv"):
            continue

        scanned += 1
        df = pd.read_csv(path)

        if "text" not in df.columns:
            print(f"skip no text column: {path}")
            skipped += 1
            continue

        mask = df["text"].astype(str).map(has_tco_links)
        if not mask.any():
            continue

        out_path = path.with_name(f"{path.stem}_scrubbed{path.suffix}")
        print(f"scrub {path} -> {out_path}")

        if not dry_run:
            df_out = df.copy()
            df_out["text"] = df_out["text"].astype(str).map(strip_tco_links)
            df_out.to_csv(out_path, index=False)

        scrubbed += 1

    print(f"scanned={scanned} scrubbed={scrubbed} skipped={skipped}")
    if dry_run:
        print("(dry-run: no files written)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write sidecar *_scrubbed.csv files with t.co removed from text",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print would-write paths only",
    )
    parser.add_argument(
        "--twitter-root",
        type=Path,
        default=TWITTER_ROOT,
        help="Root directory for Twitter CSV data",
    )
    args = parser.parse_args()
    scrub_twitter_tco_links(dry_run=args.dry_run, twitter_root=args.twitter_root)


if __name__ == "__main__":
    main()
