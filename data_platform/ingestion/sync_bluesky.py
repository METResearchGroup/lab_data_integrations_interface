from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

import yaml
from atproto import Client
from dotenv import load_dotenv

from lib.timestamp_utils import get_current_timestamp

DEFAULT_CONFIG = Path(__file__).resolve().parent / "configs/bluesky/default.yaml"
RAW_ROOT = Path(__file__).resolve().parents[1] / "data/bluesky/raw"

POSTS_RECORD_TYPE = "app.bsky.feed.post"
POSTS_CSV = "posts.csv"
POST_COLUMNS = [
    "uri",
    "url",
    "author_handle",
    "text",
    "created_at",
    "like_count",
    "repost_count",
    "reply_count",
    "quote_count",
]


def _record_type_to_filename(record_type: str) -> str:
    if record_type == POSTS_RECORD_TYPE:
        return POSTS_CSV
    return f"{record_type.rsplit('.', 1)[-1]}.csv"


def _posts_to_rows(response: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for post in response.posts:
        rkey = post.uri.split("/")[-1]
        rows.append(
            {
                "uri": post.uri,
                "url": f"https://bsky.app/profile/{post.author.handle}/post/{rkey}",
                "author_handle": post.author.handle,
                "text": post.record.text,  # type: ignore[union-attr]
                "created_at": post.record.created_at,  # type: ignore[union-attr]
                "like_count": post.like_count,
                "repost_count": post.repost_count,
                "reply_count": post.reply_count,
                "quote_count": post.quote_count,
            }
        )
    return rows


def _write_csv(rows: list[dict[str, Any]], output_path: Path, fieldnames: list[str]) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def sync_records(config_path: Path = DEFAULT_CONFIG) -> Path:
    """Fetch Bluesky records per config and write raw CSV + metadata."""
    load_dotenv()

    with config_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    fetch = config["fetch"]
    sync_timestamp = get_current_timestamp()
    output_dir = RAW_ROOT / sync_timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    client = Client()
    client.login(
        os.environ["BLUESKY_HANDLE"],
        os.environ["BLUESKY_APP_PASSWORD"],
    )

    response = client.app.bsky.feed.search_posts(
        params={
            "q": fetch["keyword"],
            "author": fetch["handle"],
            "limit": fetch["limit"],
            "sort": fetch.get("sort", "latest"),
        }
    )

    record_types: list[str] = config["record_types"]
    written_files: dict[str, str] = {}
    row_counts: dict[str, int] = {}

    if POSTS_RECORD_TYPE in record_types:
        rows = _posts_to_rows(response)
        csv_name = _record_type_to_filename(POSTS_RECORD_TYPE)
        csv_path = output_dir / csv_name
        _write_csv(rows, csv_path, POST_COLUMNS)
        written_files[POSTS_RECORD_TYPE] = csv_name
        row_counts[POSTS_RECORD_TYPE] = len(rows)

    metadata = {
        "name": config["name"],
        "description": config["description"],
        "date": config["date"],
        "sync_timestamp": sync_timestamp,
        "record_types": record_types,
        "fetch": fetch,
        "row_counts": row_counts,
        "files": written_files,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    total_rows = sum(row_counts.values())
    print(f"sync_records: wrote {total_rows} rows to {output_dir}")
    return output_dir
