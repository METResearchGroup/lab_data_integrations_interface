"""One-shot Reddit data collection experiment.

Run from repo root:

    PYTHONPATH=. uv run python experiments/reddit_fetch_data_2026_05_23/main.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from experiments.reddit_fetch_data_2026_05_23.reddit_client import (
    COMMENT_CSV_FIELDNAMES,
    CSV_FIELDNAMES,
    fetch_subreddit_posts,
    init_reddit,
)
from lib.timestamp_utils import get_current_timestamp

SUBREDDITS: list[str] = [
    "Conservative",
    "Republican",
    "AskConservatives",
    "politics",
    "liberal",
    "democrats",
]
POSTS_PER_SUBREDDIT = 10
COMMENTS_PER_POST = 100
MIN_COMMENT_BODY_LENGTH = 30


def write_metadata(
    output_dir: Path,
    sync_timestamp: str,
    subreddits: list[str],
    posts_per_subreddit: int,
    counts: dict[str, int],
    files: dict[str, str],
    *,
    comments_per_post_max: int,
    min_comment_body_length: int,
    comment_counts: dict[str, int],
    comment_files: dict[str, str],
) -> dict[str, object]:
    """Write metadata.json and return the metadata dict."""
    metadata: dict[str, object] = {
        "sync_timestamp": sync_timestamp,
        "subreddits": subreddits,
        "posts_per_subreddit": posts_per_subreddit,
        "total_posts": sum(counts.values()),
        "counts": counts,
        "files": files,
        "comments_per_post_max": comments_per_post_max,
        "min_comment_body_length": min_comment_body_length,
        "total_comments": sum(comment_counts.values()),
        "comment_counts": comment_counts,
        "comment_files": comment_files,
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


def write_comments_csv(rows: list[dict[str, object]], path: Path) -> None:
    """Write normalized comment rows to a CSV file."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COMMENT_CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    sync_timestamp = get_current_timestamp()
    output_dir = Path(__file__).parent / "data" / sync_timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    reddit = init_reddit()
    counts: dict[str, int] = {}
    files: dict[str, str] = {}
    comment_counts: dict[str, int] = {}
    comment_files: dict[str, str] = {}

    for subreddit in SUBREDDITS:
        post_rows, comment_rows = fetch_subreddit_posts(
            reddit,
            subreddit,
            limit=POSTS_PER_SUBREDDIT,
            sync_timestamp=sync_timestamp,
            comments_per_post=COMMENTS_PER_POST,
            min_comment_body_length=MIN_COMMENT_BODY_LENGTH,
        )

        post_filename = f"{subreddit.lower()}.csv"
        post_csv_path = output_dir / post_filename
        write_subreddit_csv(post_rows, post_csv_path)

        comment_filename = f"{subreddit.lower()}_comments.csv"
        comment_csv_path = output_dir / comment_filename
        write_comments_csv(comment_rows, comment_csv_path)

        key = subreddit.lower()
        counts[key] = len(post_rows)
        files[key] = post_filename
        comment_counts[key] = len(comment_rows)
        comment_files[key] = comment_filename
        print(
            f"{subreddit}: {len(post_rows)} posts, {len(comment_rows)} comments "
            f"written to {post_csv_path} and {comment_csv_path}"
        )

    write_metadata(
        output_dir=output_dir,
        sync_timestamp=sync_timestamp,
        subreddits=SUBREDDITS,
        posts_per_subreddit=POSTS_PER_SUBREDDIT,
        counts=counts,
        files=files,
        comments_per_post_max=COMMENTS_PER_POST,
        min_comment_body_length=MIN_COMMENT_BODY_LENGTH,
        comment_counts=comment_counts,
        comment_files=comment_files,
    )
    print(f"Metadata written to {output_dir / 'metadata.json'}")


if __name__ == "__main__":
    main()
