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


def _scrubbed_path(original_path: Path) -> Path:
    return original_path.with_name(f"{original_path.stem}_scrubbed{original_path.suffix}")


def _text_has_tco(df: pd.DataFrame) -> bool:
    return bool(df["text"].astype(str).map(has_tco_links).any())


def _fail(message: str) -> None:
    print(message)
    sys.exit(1)


def _verify_scrubbed_pair(
    original_path: Path,
    scrubbed_path: Path,
    orig_df: pd.DataFrame,
    scr_df: pd.DataFrame,
) -> None:
    if "text" not in scr_df.columns:
        _fail(f"FAIL scrubbed file lacks text column: {scrubbed_path}")

    if not _text_has_tco(orig_df):
        _fail(f"FAIL original has no t.co links: {original_path}")

    if _text_has_tco(scr_df):
        _fail(f"FAIL scrubbed still has t.co links: {scrubbed_path}")

    if len(scr_df) != len(orig_df):
        _fail(f"FAIL row count mismatch: {original_path} ({len(orig_df)} vs {len(scr_df)})")

    expected_text = orig_df["text"].astype(str).map(strip_tco_links).tolist()
    if scr_df["text"].tolist() != expected_text:
        _fail(f"FAIL text mismatch: {scrubbed_path}")

    if not orig_df.drop(columns=["text"]).equals(scr_df.drop(columns=["text"])):
        _fail(f"FAIL non-text columns differ: {scrubbed_path}")


def _verify_original_file(original_path: Path) -> bool:
    """Return True if a sidecar pair was verified."""
    scrubbed_path = _scrubbed_path(original_path)
    orig_df = pd.read_csv(original_path)
    has_text = "text" in orig_df.columns
    orig_has_tco = has_text and _text_has_tco(orig_df)

    if not scrubbed_path.exists():
        if orig_has_tco:
            _fail(f"FAIL missing sidecar: {original_path}")
        return False

    if not has_text:
        _fail(f"FAIL scrubbed exists but original lacks text column: {original_path}")

    scr_df = pd.read_csv(scrubbed_path)
    _verify_scrubbed_pair(original_path, scrubbed_path, orig_df, scr_df)
    print(f"PASS {original_path.name} -> {scrubbed_path.name}")
    return True


def verify_twitter_tco_scrub(*, twitter_root: Path) -> None:
    verified = sum(
        1
        for original_path in sorted(twitter_root.rglob("*.csv"))
        if not original_path.name.endswith("_scrubbed.csv") and _verify_original_file(original_path)
    )
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
