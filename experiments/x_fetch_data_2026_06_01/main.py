"""One-shot X keyword post fetch experiment.

Run from repo root:

    PYTHONPATH=. uv run python experiments/x_fetch_data_2026_06_01/main.py
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from experiments.x_fetch_data_2026_06_01.x_client import (
    CSV_FIELDNAMES,
    fetch_posts_for_keyword,
    init_x_client,
)
from lib.timestamp_utils import get_current_timestamp

logger = logging.getLogger(__name__)

TOTAL_POST_CAP = 100
POSTS_PER_KEYWORD = 10

KEYWORDS: list[str] = [
    "gun control",
    "climate change",
    "abortion",
    "immigration",
    "second amendment",
    "reproductive rights",
    "border security",
    "renewable energy",
    "pro-life",
    "DACA",
]


def write_posts_csv(rows: list[dict[str, object]], path: Path) -> None:
    """Write normalized post rows to a CSV file."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_metadata(
    output_dir: Path,
    *,
    sync_timestamp: str,
    keywords: list[str],
    total_post_cap: int,
    posts_per_keyword_target: int,
    counts_by_keyword: dict[str, int],
    total_posts: int,
) -> dict[str, object]:
    """Write metadata.json and return the metadata dict."""
    metadata: dict[str, object] = {
        "sync_timestamp": sync_timestamp,
        "api": "x_api_v2",
        "endpoint": "/2/tweets/search/recent",
        "total_post_cap": total_post_cap,
        "posts_per_keyword_target": posts_per_keyword_target,
        "total_posts": total_posts,
        "filters": {
            "original_posts_only": True,
            "exclude": ["reply", "retweet", "quote"],
            "lang": "en",
        },
        "keywords": keywords,
        "counts_by_keyword": counts_by_keyword,
        "files": {
            "posts": "posts.csv",
        },
    }
    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    return metadata


def main() -> None:
    sync_timestamp = get_current_timestamp()
    output_dir = Path(__file__).parent / "data" / sync_timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    client = init_x_client()
    all_rows: list[dict[str, object]] = []
    counts_by_keyword: dict[str, int] = {}

    for keyword in KEYWORDS:
        remaining = TOTAL_POST_CAP - len(all_rows)
        if remaining <= 0:
            break

        limit = min(POSTS_PER_KEYWORD, remaining)
        try:
            rows = fetch_posts_for_keyword(
                client,
                keyword,
                limit=limit,
                sync_timestamp=sync_timestamp,
            )
        except Exception:
            logger.exception(
                "Failed to fetch posts for keyword=%r limit=%s sync_timestamp=%s",
                keyword,
                limit,
                sync_timestamp,
            )
            rows = []
        all_rows.extend(rows)
        counts_by_keyword[keyword] = len(rows)
        print(f"{keyword}: {len(rows)} posts")

    posts_csv_path = output_dir / "posts.csv"
    write_posts_csv(all_rows, posts_csv_path)

    write_metadata(
        output_dir=output_dir,
        sync_timestamp=sync_timestamp,
        keywords=KEYWORDS,
        total_post_cap=TOTAL_POST_CAP,
        posts_per_keyword_target=POSTS_PER_KEYWORD,
        counts_by_keyword=counts_by_keyword,
        total_posts=len(all_rows),
    )
    print(f"Metadata written to {output_dir / 'metadata.json'}")


if __name__ == "__main__":
    main()
