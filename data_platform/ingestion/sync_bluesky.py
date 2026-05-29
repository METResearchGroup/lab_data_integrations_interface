from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import typer
import yaml
from atproto import Client

from lib.load_env_vars import EnvVarsContainer
from lib.timestamp_utils import get_current_timestamp

CONFIGS_DIR = Path(__file__).resolve().parent / "configs/bluesky"
DEFAULT_CONFIG = CONFIGS_DIR / "default.yaml"
RAW_ROOT = Path(__file__).resolve().parents[1] / "data/bluesky/raw"
API_MAX_LIMIT = 100

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
    """Build a single searchPosts q string that ORs all keywords together."""
    return " OR ".join(_quote_query_term(keyword) for keyword in keywords)


def _iter_fetch_queries(fetch: dict[str, Any]) -> list[tuple[str, str]]:
    keyword = fetch.get("keyword")
    if isinstance(keyword, list):
        return [("posts", build_or_query(keyword))]
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


def _page_limit(fetch: dict[str, Any], rows_so_far: int, max_rows: int) -> int:
    per_page = min(int(fetch["limit"]), API_MAX_LIMIT)
    remaining = max_rows - rows_so_far
    return min(per_page, remaining)


def fetch_posts_with_pagination(
    client: Client,
    fetch: dict[str, Any],
    query: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch posts using searchPosts cursor pagination up to max_rows."""
    max_rows = int(fetch.get("max_rows", fetch["limit"]))
    rows_by_uri: dict[str, dict[str, Any]] = {}
    cursor: str | None = None
    pages_fetched = 0
    hits_total: int | None = None

    while len(rows_by_uri) < max_rows:
        page_limit = _page_limit(fetch, len(rows_by_uri), max_rows)
        if page_limit <= 0:
            break

        response = _search_posts_page(
            client,
            fetch,
            query,
            page_limit=page_limit,
            cursor=cursor,
        )
        pages_fetched += 1
        if response.hits_total is not None:
            hits_total = response.hits_total

        for row in _posts_to_rows(response):
            rows_by_uri.setdefault(row["uri"], row)

        if not response.posts or not response.cursor:
            break
        cursor = response.cursor

    pagination = {
        "pages_fetched": pages_fetched,
        "hits_total": hits_total,
        "max_rows": max_rows,
        "page_limit": min(int(fetch["limit"]), API_MAX_LIMIT),
        "rows_collected": len(rows_by_uri),
        "reached_max_rows": len(rows_by_uri) >= max_rows and cursor is not None,
    }
    return list(rows_by_uri.values()), pagination


def export_synced_records(
    rows: list[dict[str, Any]],
    output_dir: Path,
    output_stem: str,
) -> str:
    csv_name = _record_type_to_filename(POSTS_RECORD_TYPE, output_stem)
    csv_path = output_dir / csv_name
    _write_csv(rows, csv_path, POST_COLUMNS)
    return csv_name


def fetch_and_export_post_records(
    client: Client,
    fetch: dict[str, Any],
    output_dir: Path,
) -> tuple[dict[str, str], dict[str, int], dict[str, dict[str, Any]]]:
    written_files: dict[str, str] = {}
    row_counts: dict[str, int] = {}
    pagination_stats: dict[str, dict[str, Any]] = {}

    for output_stem, query in _iter_fetch_queries(fetch):
        rows, pagination = fetch_posts_with_pagination(client, fetch, query)
        csv_name = export_synced_records(rows, output_dir, output_stem)
        file_key = f"{POSTS_RECORD_TYPE}/{output_stem}"
        written_files[file_key] = csv_name
        row_counts[file_key] = len(rows)
        pagination_stats[file_key] = pagination
        print(
            f"sync_records: {output_stem} -> {len(rows)} rows "
            f"({pagination['pages_fetched']} pages, max_rows={pagination['max_rows']})"
        )

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
        candidates.extend(CONFIGS_DIR / candidate.name for candidate in candidates)

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
