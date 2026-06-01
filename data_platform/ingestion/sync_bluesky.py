"""Sync Bluesky posts from YAML config to raw CSV storage.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py --config mirrorview.yaml

Resume the latest in-progress run for a dataset:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py \\
        --config mirrorview_scale.yaml --resume

Resume a specific raw run timestamp:

    PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py \\
        --config mirrorview_scale.yaml --resume --run-dir 2026_05_30-12:00:00

Ingestion YAML must include `dataset_id` (e.g. bluesky_<uuid>).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import typer
from atproto import Client
from tqdm import tqdm

from data_platform.ingestion.bluesky_retry import retry_bluesky_request
from data_platform.utils.config_paths import load_yaml_config, resolve_config_path
from data_platform.utils.dataset import validate_dataset_id, write_dataset_manifest
from data_platform.utils.storage import BlueskyStorageManager
from lib.load_env_vars import EnvVarsContainer
from lib.timestamp_utils import get_current_timestamp

CONFIGS_DIR = Path(__file__).resolve().parent / "configs/bluesky"
DEFAULT_CONFIG = CONFIGS_DIR / "default.yaml"
API_MAX_LIMIT = 100

POSTS_RECORD_TYPE = "app.bsky.feed.post"
POSTS_CSV = "posts.csv"
DEFAULT_QUERY_BATCH_SIZE = 5

KeywordStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]
SyncStatus = Literal["in_progress", "completed"]


@dataclass(frozen=True)
class FetchWorkItem:
    batch_label: str
    query: str
    ledger_key: str
    keywords_in_batch: list[str] | None = None


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


def iter_fetch_work_items(fetch: dict[str, Any]) -> list[FetchWorkItem]:
    """Return work items as (batch_label, query, ledger_key) for checkpointing."""
    keyword = fetch.get("keyword")
    batch_size = _query_batch_size(fetch)
    if isinstance(keyword, list):
        items: list[FetchWorkItem] = []
        for index, chunk in enumerate(_chunk_keywords(keyword, batch_size)):
            batch_label = f"posts_batch_{index + 1}"
            query = build_or_query(chunk)
            if batch_size == 1:
                ledger_key = chunk[0]
                keywords_in_batch = None
            else:
                ledger_key = batch_label
                keywords_in_batch = chunk
            items.append(
                FetchWorkItem(
                    batch_label=batch_label,
                    query=query,
                    ledger_key=ledger_key,
                    keywords_in_batch=keywords_in_batch,
                )
            )
        return items
    if isinstance(keyword, str) and keyword:
        return [
            FetchWorkItem(
                batch_label="posts",
                query=keyword,
                ledger_key=keyword,
            )
        ]

    raise ValueError("fetch config must include 'keyword' as a string or list of strings")


def _iter_fetch_queries(fetch: dict[str, Any]) -> list[tuple[str, str]]:
    return [(item.batch_label, item.query) for item in iter_fetch_work_items(fetch)]


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


@retry_bluesky_request()
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


def fetch_posts_for_keyword(
    client: Client,
    fetch: dict[str, Any],
    query: str,
    *,
    batch_label: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch up to fetch.limit posts for a single query, paginating with cursor."""
    target = int(fetch["limit"])
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    pages_fetched = 0
    hits_total: int | None = None

    while len(rows) < target:
        page_limit = min(target - len(rows), API_MAX_LIMIT)
        response = _search_posts_page(client, fetch, query, page_limit=page_limit, cursor=cursor)
        if pages_fetched == 0:
            hits_total = response.hits_total
        page_rows = _posts_to_rows(response)
        if not page_rows:
            break
        rows.extend(page_rows)
        pages_fetched += 1
        cursor = response.cursor
        if not cursor:
            break

    rows = rows[:target]
    stats = {
        "batch_label": batch_label,
        "query_len": len(query),
        "per_query_limit": target,
        "pages_fetched": pages_fetched,
        "rows_collected": len(rows),
        "hits_total": hits_total,
    }
    return rows, stats


def _keyword_entry(item: FetchWorkItem) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "status": "pending",
        "batch_label": item.batch_label,
        "pages_fetched": 0,
        "rows_collected": 0,
        "hits_total": None,
        "last_error": None,
    }
    if item.keywords_in_batch is not None:
        entry["keywords_in_batch"] = item.keywords_in_batch
    return entry


def init_sync_metadata(
    config: dict[str, Any],
    config_path: Path,
    sync_timestamp: str,
    work_items: list[FetchWorkItem],
) -> dict[str, Any]:
    dataset_id = _require_dataset_id(config)
    return {
        "sync_status": "in_progress",
        "dataset_id": dataset_id,
        "name": config["name"],
        "description": config["description"],
        "date": config["date"],
        "sync_timestamp": sync_timestamp,
        "ingestion_config": config_path.name,
        "record_types": config["record_types"],
        "fetch": config["fetch"],
        "row_count": 0,
        "keywords": {item.ledger_key: _keyword_entry(item) for item in work_items},
    }


def _flush_metadata(
    storage: BlueskyStorageManager, run_dir: Path, metadata: dict[str, Any]
) -> None:
    storage.write_run_metadata_atomic(run_dir, metadata)


def _mark_remaining_skipped(metadata: dict[str, Any]) -> None:
    for entry in metadata["keywords"].values():
        if entry["status"] == "pending":
            entry["status"] = "skipped"


def _sync_status_done(metadata: dict[str, Any]) -> SyncStatus:
    statuses = {entry["status"] for entry in metadata["keywords"].values()}
    unfinished = statuses - {"completed", "skipped"}
    return "completed" if not unfinished else "in_progress"


def run_keyword_sync_loop(
    client: Client,
    fetch: dict[str, Any],
    output_dir: Path,
    storage: BlueskyStorageManager,
    metadata: dict[str, Any],
    work_items: list[FetchWorkItem],
    *,
    csv_filename: str,
) -> None:
    max_rows = fetch.get("max_rows")
    max_rows_int = int(max_rows) if max_rows is not None else None

    for item in tqdm(
        work_items,
        desc="Syncing keywords",
        disable=not sys.stderr.isatty(),
    ):
        entry = metadata["keywords"][item.ledger_key]
        status = entry["status"]
        if status in ("completed", "skipped"):
            continue

        if max_rows_int is not None and metadata["row_count"] >= max_rows_int:
            _mark_remaining_skipped(metadata)
            _flush_metadata(storage, output_dir, metadata)
            break

        entry["status"] = "in_progress"
        entry["last_error"] = None
        _flush_metadata(storage, output_dir, metadata)

        try:
            rows, stats = fetch_posts_for_keyword(
                client,
                fetch,
                item.query,
                batch_label=item.batch_label,
            )
        except Exception as exc:  # noqa: BLE001 — record and continue
            entry["status"] = "failed"
            entry["last_error"] = str(exc)
            _flush_metadata(storage, output_dir, metadata)
            print(f"sync_records: {item.ledger_key} failed: {exc}")
            continue

        seen_uris = storage.load_seen_uris(output_dir, filename=csv_filename)
        new_rows = [row for row in rows if row["uri"] not in seen_uris]
        if new_rows:
            storage.append_records(new_rows, output_dir, filename=csv_filename)

        metadata["row_count"] = len(storage.load_seen_uris(output_dir, filename=csv_filename))
        entry["status"] = "completed"
        entry["pages_fetched"] = stats["pages_fetched"]
        entry["rows_collected"] = stats["rows_collected"]
        entry["hits_total"] = stats["hits_total"]
        entry["last_error"] = None
        _flush_metadata(storage, output_dir, metadata)

        print(
            f"sync_records: {item.ledger_key} -> {stats['rows_collected']} rows "
            f"(appended {len(new_rows)}, pages={stats['pages_fetched']})"
        )

        if max_rows_int is not None and metadata["row_count"] >= max_rows_int:
            _mark_remaining_skipped(metadata)
            _flush_metadata(storage, output_dir, metadata)
            break

    metadata["sync_status"] = _sync_status_done(metadata)
    _flush_metadata(storage, output_dir, metadata)


def find_resume_run_dir(
    storage: BlueskyStorageManager,
    *,
    run_dir_name: str | None,
) -> Path:
    if run_dir_name is not None:
        run_dir = storage.root_dir / run_dir_name
        if not run_dir.is_dir():
            raise FileNotFoundError(f"Run directory not found: {run_dir}")
        return run_dir

    if not storage.root_dir.exists():
        raise FileNotFoundError(f"No raw runs found under {storage.root_dir}")

    candidates: list[tuple[str, Path]] = []
    for path in storage.root_dir.iterdir():
        if not path.is_dir():
            continue
        metadata_path = path / "metadata.json"
        if not metadata_path.exists():
            continue
        metadata = storage.load_run_metadata(path)
        if metadata.get("sync_status") == "in_progress":
            candidates.append((path.name, path))

    if not candidates:
        raise FileNotFoundError(
            f"No in-progress raw run found under {storage.root_dir}. "
            "Start a new sync or pass --run-dir."
        )
    return max(candidates, key=lambda item: item[0])[1]


def merge_work_items_with_metadata(
    work_items: list[FetchWorkItem],
    metadata: dict[str, Any],
) -> list[FetchWorkItem]:
    ledger_keys = {item.ledger_key for item in work_items}
    metadata_keys = set(metadata.get("keywords", {}))
    missing = ledger_keys - metadata_keys
    extra = metadata_keys - ledger_keys
    if missing or extra:
        raise ValueError(
            "Config keywords do not match resume metadata "
            f"(missing in metadata: {sorted(missing)}, extra in metadata: {sorted(extra)})"
        )
    return work_items


load_config = load_yaml_config


def _require_dataset_id(config: dict[str, Any]) -> str:
    raw = config.get("dataset_id")
    if not raw:
        raise ValueError("ingestion config must include dataset_id (bluesky_<uuid>)")
    return validate_dataset_id(str(raw))


def setup_client() -> Client:
    client = Client()
    client.login(
        EnvVarsContainer.get_env_var("BLUESKY_HANDLE", required=True),
        EnvVarsContainer.get_env_var("BLUESKY_PASSWORD", required=True),
    )
    return client


def sync_records(
    config_path: Path = DEFAULT_CONFIG,
    *,
    resume: bool = False,
    run_dir_name: str | None = None,
) -> Path:
    """Fetch Bluesky records per config and write raw CSV + metadata."""
    if run_dir_name is not None and not resume:
        raise ValueError("--run-dir requires --resume")

    config = load_config(config_path)
    dataset_id = _require_dataset_id(config)
    storage = BlueskyStorageManager("raw", dataset_id)

    manifest_path = storage.root_dir.parent / "dataset.json"
    if not manifest_path.exists():
        write_dataset_manifest(
            "bluesky",
            dataset_id,
            name=str(config["name"]),
            ingestion_config=str(config_path.relative_to(Path(__file__).resolve().parents[2])),
        )

    fetch = config["fetch"]
    work_items = iter_fetch_work_items(fetch)
    record_types: list[str] = config["record_types"]

    if POSTS_RECORD_TYPE not in record_types:
        raise ValueError(f"Unsupported record types for checkpoint sync: {record_types}")

    csv_filename = _record_type_to_filename(POSTS_RECORD_TYPE, "posts")
    client = setup_client()

    if resume:
        output_dir = find_resume_run_dir(storage, run_dir_name=run_dir_name)
        metadata = storage.load_run_metadata(output_dir)
        if metadata.get("sync_status") != "in_progress":
            metadata["sync_status"] = "in_progress"
            _flush_metadata(storage, output_dir, metadata)
        work_items = merge_work_items_with_metadata(work_items, metadata)
        print(f"sync_records: resuming {output_dir}")
    else:
        sync_timestamp = get_current_timestamp()
        output_dir = storage.create_new_run_dir(sync_timestamp)
        metadata = init_sync_metadata(config, config_path, sync_timestamp, work_items)
        _flush_metadata(storage, output_dir, metadata)
        print(f"sync_records: started new run {output_dir}")

    run_keyword_sync_loop(
        client,
        fetch,
        output_dir,
        storage,
        metadata,
        work_items,
        csv_filename=csv_filename,
    )

    total_rows = metadata["row_count"]
    print(
        f"sync_records: wrote {total_rows} rows to {output_dir} (status={metadata['sync_status']})"
    )
    return output_dir


def main(
    config: Path = typer.Option(
        DEFAULT_CONFIG,
        "--config",
        help="YAML config path or filename under configs/bluesky/ (e.g. mirrorview.yaml)",
    ),
    resume: bool = typer.Option(
        False,
        "--resume",
        help="Resume the latest in-progress raw run for this dataset",
    ),
    run_dir: str | None = typer.Option(
        None,
        "--run-dir",
        help="Raw run timestamp directory name (requires --resume)",
    ),
) -> None:
    config_path = resolve_config_path(config, CONFIGS_DIR)
    sync_records(config_path, resume=resume, run_dir_name=run_dir)


if __name__ == "__main__":
    typer.run(main)
