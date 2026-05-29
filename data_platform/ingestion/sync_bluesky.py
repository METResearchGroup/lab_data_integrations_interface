"""Sync Bluesky posts from YAML config to raw CSV storage.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py --config mirrorview.yaml
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import typer
import yaml
from atproto import Client
from tqdm import tqdm

from data_platform.models.sync import SyncBlueskyPostModel
from lib.load_env_vars import EnvVarsContainer
from lib.timestamp_utils import get_current_timestamp

CONFIGS_DIR = Path(__file__).resolve().parent / "configs/bluesky"
DEFAULT_CONFIG = CONFIGS_DIR / "default.yaml"
RAW_ROOT = Path(__file__).resolve().parents[1] / "data/bluesky/raw"
API_MAX_LIMIT = 100

POSTS_RECORD_TYPE = "app.bsky.feed.post"
POSTS_CSV = "posts.csv"
DEFAULT_QUERY_BATCH_SIZE = 5


def _record_type_to_filename(record_type: str, output_stem: str = "posts") -> str:
    if record_type == POSTS_RECORD_TYPE:
        return f"{output_stem}.csv"
    return f"{record_type.rsplit('.', 1)[-1]}.csv"


def _quote_query_term(keyword: str) -> str:
    if any(ch.isspace() for ch in keyword) or any(ch in keyword for ch in ('"', ":", "(", ")")):
        escaped = keyword.replace('"', '\\"')
        return f'"{escaped}"'
    return keyword


def build_or_query(keywords: list[str]) -> str:
    """Build a searchPosts q string using Bluesky's pipe-delimited OR syntax."""
    return " | ".join(_quote_query_term(keyword) for keyword in keywords)


def _query_batch_size(fetch: dict[str, Any]) -> int:
    return int(fetch.get("query_batch_size", DEFAULT_QUERY_BATCH_SIZE))


def _chunk_keywords(keywords: list[str], batch_size: int) -> list[list[str]]:
    return [keywords[i : i + batch_size] for i in range(0, len(keywords), batch_size)]


def _iter_fetch_queries(fetch: dict[str, Any]) -> list[tuple[str, str]]:
    keyword = fetch.get("keyword")
    if isinstance(keyword, list):
        chunks = _chunk_keywords(keyword, _query_batch_size(fetch))
        return [
            (f"posts_batch_{index + 1}", build_or_query(chunk))
            for index, chunk in enumerate(chunks)
        ]
    if isinstance(keyword, str) and keyword:
        return [("posts", keyword)]

    raise ValueError("fetch config must include 'keyword' as a string or list of strings")


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


def _search_posts_page(
    client: Client,
    fetch: dict[str, Any],
    query: str,
    *,
    page_limit: int,
    cursor: str | None = None,
) -> Any:
    base_params = {
        "q": query,
        "limit": page_limit,
        "sort": fetch.get("sort", "latest"),
    }
    if cursor:
        base_params["cursor"] = cursor
    handle = fetch.get("handle")
    if handle:
        return client.app.bsky.feed.search_posts(
            params={**base_params, "author": handle},  # type: ignore[arg-type]
        )
    return client.app.bsky.feed.search_posts(params=base_params)  # type: ignore[arg-type]


def fetch_posts_for_batch(
    client: Client,
    fetch: dict[str, Any],
    query: str,
    *,
    batch_label: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch up to fetch.limit posts for a single batched query."""
    batch_limit = min(int(fetch["limit"]), API_MAX_LIMIT)
    response = _search_posts_page(client, fetch, query, page_limit=batch_limit)
    rows = _posts_to_rows(response)
    stats = {
        "batch_label": batch_label,
        "query_len": len(query),
        "limit": batch_limit,
        "rows_collected": len(rows),
        "hits_total": response.hits_total,
    }
    return rows, stats


def _rows_to_validated_dicts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [SyncBlueskyPostModel.model_validate(row).model_dump() for row in rows]


def export_synced_records(
    rows: list[dict[str, Any]],
    output_dir: Path,
    output_stem: str,
) -> str:
    csv_name = _record_type_to_filename(POSTS_RECORD_TYPE, output_stem)
    csv_path = output_dir / csv_name
    validated_rows = _rows_to_validated_dicts(rows)
    fieldnames = list(SyncBlueskyPostModel.model_fields.keys())
    _write_csv(validated_rows, csv_path, fieldnames)
    return csv_name


def fetch_and_export_post_records(
    client: Client,
    fetch: dict[str, Any],
    output_dir: Path,
) -> tuple[dict[str, str], dict[str, int], dict[str, dict[str, Any]]]:
    queries = _iter_fetch_queries(fetch)
    keyword = fetch.get("keyword")
    keyword_count = len(keyword) if isinstance(keyword, list) else 1
    batch_size = _query_batch_size(fetch) if isinstance(keyword, list) else 1
    per_batch_limit = min(int(fetch["limit"]), API_MAX_LIMIT)
    batch_count = len(queries)

    rows_by_uri: dict[str, dict[str, Any]] = {}
    batch_stats: dict[str, dict[str, Any]] = {}

    for batch_label, query in tqdm(
        queries,
        desc="Syncing batches",
        disable=not sys.stderr.isatty(),
    ):
        rows, stats = fetch_posts_for_batch(
            client, fetch, query, batch_label=batch_label
        )
        batch_stats[batch_label] = stats
        for row in rows:
            rows_by_uri.setdefault(row["uri"], row)
        print(
            f"sync_records: {batch_label} -> {stats['rows_collected']} rows "
            f"(query_len={stats['query_len']}, limit={stats['limit']})"
        )

    all_rows = list(rows_by_uri.values())
    max_rows = fetch.get("max_rows")
    if max_rows is not None:
        all_rows = all_rows[: int(max_rows)]

    csv_name = export_synced_records(all_rows, output_dir, "posts")
    file_key = f"{POSTS_RECORD_TYPE}/posts"
    written_files = {file_key: csv_name}
    row_counts = {file_key: len(all_rows)}
    pagination_stats = {
        file_key: {
            "query_batch_size": batch_size,
            "keyword_count": keyword_count,
            "batch_count": batch_count,
            "per_batch_limit": per_batch_limit,
            "expected_max_rows": batch_count * per_batch_limit,
            "rows_collected": len(all_rows),
            "batches": batch_stats,
        }
    }

    return written_files, row_counts, pagination_stats


def write_metadata(output_dir: Path, metadata: dict[str, Any]) -> None:
    metadata_path = output_dir / "metadata.json"
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def load_config(config_path: Path) -> dict[str, Any]:
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_config_path(config: Path) -> Path:
    candidates = [config]
    if config.suffix != ".yaml":
        candidates.append(config.with_suffix(".yaml"))
    if config.parent == Path("."):
        candidates.extend(
            CONFIGS_DIR / candidate.name for candidate in list(candidates)
        )

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    raise FileNotFoundError(f"Config not found: {config}")


def setup_client() -> Client:
    client = Client()
    client.login(
        EnvVarsContainer.get_env_var("BLUESKY_HANDLE", required=True),
        EnvVarsContainer.get_env_var("BLUESKY_PASSWORD", required=True),
    )
    return client


def sync_records(config_path: Path = DEFAULT_CONFIG) -> Path:
    """Fetch Bluesky records per config and write raw CSV + metadata."""
    config = load_config(config_path)

    fetch = config["fetch"]
    sync_timestamp = get_current_timestamp()
    output_dir = RAW_ROOT / sync_timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    client = setup_client()

    record_types: list[str] = config["record_types"]
    written_files: dict[str, str] = {}
    row_counts: dict[str, int] = {}
    pagination_stats: dict[str, dict[str, Any]] = {}

    if POSTS_RECORD_TYPE in record_types:
        written_files, row_counts, pagination_stats = fetch_and_export_post_records(
            client, fetch, output_dir
        )

    metadata = {
        "name": config["name"],
        "description": config["description"],
        "date": config["date"],
        "sync_timestamp": sync_timestamp,
        "record_types": record_types,
        "fetch": fetch,
        "row_counts": row_counts,
        "pagination": pagination_stats,
        "files": written_files,
    }
    write_metadata(output_dir, metadata)

    total_rows = sum(row_counts.values())
    print(f"sync_records: wrote {total_rows} rows across {len(row_counts)} files to {output_dir}")
    return output_dir


def main(
    config: Path = typer.Option(
        DEFAULT_CONFIG,
        "--config",
        help="YAML config path or filename under configs/bluesky/ (e.g. mirrorview.yaml)",
    ),
) -> None:
    config_path = resolve_config_path(config)
    sync_records(config_path)


if __name__ == "__main__":
    typer.run(main)
