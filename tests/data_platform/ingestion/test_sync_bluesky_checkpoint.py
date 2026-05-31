from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from data_platform.ingestion import sync_bluesky
from data_platform.utils.storage import BlueskyStorageManager
from tests.data_platform.constants import VALID_DATASET_ID
from tests.data_platform.conftest import make_ingestion_row
from tests.data_platform.ingestion.conftest import (
    minimal_sync_config,
    mock_post,
    mock_search_response,
)


def test_init_sync_metadata_keyword_ledger() -> None:
    config = minimal_sync_config()
    work_items = sync_bluesky.iter_fetch_work_items(config["fetch"])
    metadata = sync_bluesky.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        work_items,
    )
    assert metadata["sync_status"] == "in_progress"
    assert set(metadata["keywords"]) == {"alpha", "beta"}
    assert metadata["keywords"]["alpha"]["status"] == "pending"


def test_run_keyword_sync_loop_appends_per_keyword(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = minimal_sync_config()
    fetch = config["fetch"]
    work_items = sync_bluesky.iter_fetch_work_items(fetch)
    storage = BlueskyStorageManager("raw", VALID_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_bluesky.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        work_items,
    )

    posts_by_query = {
        "alpha": [mock_post("at://did:plc:ex/app.bsky.feed.post/a1")],
        "beta": [mock_post("at://did:plc:ex/app.bsky.feed.post/b1")],
    }

    def fake_search(
        client: Any,
        fetch_cfg: dict[str, Any],
        query: str,
        *,
        page_limit: int,
        cursor: str | None = None,
    ):
        return mock_search_response(posts_by_query[query])

    monkeypatch.setattr(sync_bluesky, "_search_posts_page", fake_search)

    sync_bluesky.run_keyword_sync_loop(
        MagicMock(),
        fetch,
        run_dir,
        storage,
        metadata,
        work_items,
        csv_filename="posts.csv",
    )

    assert metadata["keywords"]["alpha"]["status"] == "completed"
    assert metadata["keywords"]["beta"]["status"] == "completed"
    assert metadata["row_count"] == 2
    assert metadata["sync_status"] == "completed"
    assert len(storage.load_seen_uris(run_dir)) == 2


def test_resume_skips_completed_keywords(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = minimal_sync_config()
    fetch = config["fetch"]
    work_items = sync_bluesky.iter_fetch_work_items(fetch)
    storage = BlueskyStorageManager("raw", VALID_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_bluesky.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        work_items,
    )
    metadata["keywords"]["alpha"]["status"] = "completed"
    metadata["keywords"]["alpha"]["rows_collected"] = 1
    storage.append_records(
        [
            make_ingestion_row(
                uri="at://did:plc:ex/app.bsky.feed.post/a1",
                url="https://bsky.app/profile/user/post/a1",
                author_handle="user",
                text="x",
            )
        ],
        run_dir,
    )
    metadata["row_count"] = 1
    storage.write_run_metadata_atomic(run_dir, metadata)

    calls: list[str] = []

    def fake_search(
        client: Any,
        fetch_cfg: dict[str, Any],
        query: str,
        *,
        page_limit: int,
        cursor: str | None = None,
    ):
        calls.append(query)
        return mock_search_response([mock_post("at://did:plc:ex/app.bsky.feed.post/b1")])

    monkeypatch.setattr(sync_bluesky, "_search_posts_page", fake_search)

    resumed_metadata = storage.load_run_metadata(run_dir)
    sync_bluesky.run_keyword_sync_loop(
        MagicMock(),
        fetch,
        run_dir,
        storage,
        resumed_metadata,
        work_items,
        csv_filename="posts.csv",
    )

    assert calls == ["beta"]
    assert resumed_metadata["keywords"]["beta"]["status"] == "completed"
    assert resumed_metadata["row_count"] == 2
