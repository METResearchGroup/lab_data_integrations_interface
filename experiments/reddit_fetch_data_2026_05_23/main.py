"""One-shot Reddit data collection experiment."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.timestamp_utils import get_current_timestamp

from reddit_client import CSV_FIELDNAMES, fetch_subreddit_posts, init_reddit

SUBREDDITS: list[str] = [
    "Conservative",
    "Republican",
    "AskConservatives",
    "politics",
    "liberal",
    "democrats",
]
POSTS_PER_SUBREDDIT = 10


def write_metadata(
    output_dir: Path,
    sync_timestamp: str,
    subreddits: list[str],
    posts_per_subreddit: int,
    counts: dict[str, int],
    files: dict[str, str],
) -> dict[str, object]:
    """Write metadata.json and return the metadata dict."""
    metadata: dict[str, object] = {
        "sync_timestamp": sync_timestamp,
        "subreddits": subreddits,
        "posts_per_subreddit": posts_per_subreddit,
        "total_posts": sum(counts.values()),
        "counts": counts,
        "files": files,
    }
    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    return metadata


def write_subreddit_csv(rows: list[dict[str, object]], path: Path) -> None:
    """Write normalized post rows to a CSV file."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    sync_timestamp = get_current_timestamp()
    output_dir = Path(__file__).parent / "data" / sync_timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    reddit = init_reddit()
    counts: dict[str, int] = {}
    files: dict[str, str] = {}

    for subreddit in SUBREDDITS:
        rows = fetch_subreddit_posts(
            reddit,
            subreddit,
            limit=POSTS_PER_SUBREDDIT,
            sync_timestamp=sync_timestamp,
        )
        filename = f"{subreddit.lower()}.csv"
        csv_path = output_dir / filename
        write_subreddit_csv(rows, csv_path)

        key = subreddit.lower()
        counts[key] = len(rows)
        files[key] = filename
        print(f"{subreddit}: {len(rows)} rows written to {csv_path}")

    write_metadata(
        output_dir=output_dir,
        sync_timestamp=sync_timestamp,
        subreddits=SUBREDDITS,
        posts_per_subreddit=POSTS_PER_SUBREDDIT,
        counts=counts,
        files=files,
    )
    print(f"Metadata written to {output_dir / 'metadata.json'}")


if __name__ == "__main__":
    main()
