"""Consolidate labels/tmp/{date}/*.parquet into labels/{date}.parquet.

Merges every flushed chunk for a day into a single Parquet file, then removes
the tmp directory for that date.

Run from repo root:

    PYTHONPATH=. uv run python experiments/perspective_api_labeling_2026_08_11/consolidate_labels.py \\
        --date 2026-08-09
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd

EXPERIMENT_DIR = Path(__file__).resolve().parent
LABELS_DIR = EXPERIMENT_DIR / "labels"


def consolidate_date(date: str, *, keep_tmp: bool = False) -> Path:
    tmp_dir = LABELS_DIR / "tmp" / date
    if not tmp_dir.exists():
        raise FileNotFoundError(f"No tmp labels directory for date {date}: {tmp_dir}")

    chunk_paths = sorted(
        path for path in tmp_dir.glob("*.parquet") if not path.name.startswith(".")
    )
    if not chunk_paths:
        raise FileNotFoundError(f"No Parquet chunks under {tmp_dir}")

    print(f"date: {date}")
    print(f"chunks: {len(chunk_paths)}")

    frames = [pd.read_parquet(path) for path in chunk_paths]
    combined = pd.concat(frames, ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(subset=["uri"], keep="last")
    after = len(combined)
    if before != after:
        print(f"deduped uri: {before:,} -> {after:,}")

    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = LABELS_DIR / f"{date}.parquet"
    combined.to_parquet(output_path, index=False)
    print(f"wrote {after:,} rows -> {output_path.relative_to(EXPERIMENT_DIR)}")

    if keep_tmp:
        print(f"kept tmp dir: {tmp_dir}")
    else:
        shutil.rmtree(tmp_dir)
        print(f"cleared {tmp_dir.relative_to(EXPERIMENT_DIR)}")

    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge labels/tmp/{date}/*.parquet into labels/{date}.parquet"
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Partition date YYYY-MM-DD whose tmp chunks should be consolidated",
    )
    parser.add_argument(
        "--keep-tmp",
        action="store_true",
        help="Do not delete labels/tmp/{date} after writing the consolidated file",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    consolidate_date(args.date, keep_tmp=args.keep_tmp)


if __name__ == "__main__":
    main()
