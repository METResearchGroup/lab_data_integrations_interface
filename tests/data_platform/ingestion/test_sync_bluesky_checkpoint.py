from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from data_platform.ingestion import sync_bluesky
from data_platform.ingestion.sync_checkpoint import validate_tasks_for_resume
from data_platform.utils.storage import BlueskyStorageManager, StorageStage
from tests.data_platform.conftest import make_ingestion_row
from tests.data_platform.constants import VALID_DATASET_ID
from tests.data_platform.ingestion.conftest import (
    minimal_sync_config,
    mock_post,
    mock_search_response,
)


def test_build_sync_tasks_requires_keywords_list() -> None:
    with pytest.raises(ValueError, match="keywords"):
        sync_bluesky.build_sync_tasks({})
    with pytest.raises(ValueError, match="non-empty strings"):
        sync_bluesky.build_sync_tasks({"keywords": ["alpha", ""]})


def test_build_sync_tasks_quotes_keywords_with_spaces() -> None:
    tasks = sync_bluesky.build_sync_tasks({"keywords": ["gun control"]})
    assert len(tasks) == 1
    assert tasks[0].task_id == "gun control"
    assert tasks[0].query == '"gun control"'


def test_init_sync_metadata_task_ledger() -> None:
    config = minimal_sync_config()
    sync_tasks = sync_bluesky.build_sync_tasks(config["ingestion_params"])
    metadata = sync_bluesky.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )
    assert metadata["sync_status"] == "in_progress"
    assert set(metadata["tasks"]) == {"alpha", "beta"}
    assert metadata["tasks"]["alpha"]["status"] == "pending"
    assert metadata["tasks"]["alpha"]["kind"] == "bluesky"


def test_run_sync_tasks_appends_per_keyword(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = minimal_sync_config()
    ingestion_params = config["ingestion_params"]
    sync_tasks = sync_bluesky.build_sync_tasks(ingestion_params)
    storage = BlueskyStorageManager(StorageStage.RAW, VALID_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_bluesky.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
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

    sync_bluesky.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        storage,
        metadata,
        sync_tasks,
        filename=storage.records_filename,
    )

    assert metadata["tasks"]["alpha"]["status"] == "completed"
    assert metadata["tasks"]["beta"]["status"] == "completed"
    assert metadata["row_count"] == 2
    assert len(storage.load_seen_uris(run_dir)) == 2


def test_run_sync_tasks_skips_ids_from_other_dataset(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other_dataset_id = "bluesky_00000000-0000-4000-8000-000000000002"
    config = minimal_sync_config()
    ingestion_params = config["ingestion_params"]
    sync_tasks = sync_bluesky.build_sync_tasks(ingestion_params)
    other_storage = BlueskyStorageManager(StorageStage.RAW, other_dataset_id)
    other_run = other_storage.create_new_run_dir("2026_05_29-10:00:00")
    other_storage.append_records(
        [
            make_ingestion_row(
                uri="at://did:plc:ex/app.bsky.feed.post/old",
                url="https://bsky.app/profile/user/post/old",
                author_handle="user",
                text="old",
            )
        ],
        other_run,
    )

    storage = BlueskyStorageManager(StorageStage.RAW, VALID_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_bluesky.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )

    def fake_search(
        client: Any,
        fetch_cfg: dict[str, Any],
        query: str,
        *,
        page_limit: int,
        cursor: str | None = None,
    ):
        return mock_search_response(
            [
                mock_post("at://did:plc:ex/app.bsky.feed.post/old"),
                mock_post("at://did:plc:ex/app.bsky.feed.post/new"),
            ]
        )

    monkeypatch.setattr(sync_bluesky, "_search_posts_page", fake_search)
    monkeypatch.setattr(
        storage, "load_seen_ids_from_athena", lambda: {"at://did:plc:ex/app.bsky.feed.post/old"}
    )

    sync_bluesky.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        storage,
        metadata,
        sync_tasks[:1],
        filename=storage.records_filename,
    )

    assert storage.load_seen_uris(run_dir) == {"at://did:plc:ex/app.bsky.feed.post/new"}
    assert metadata["posts_skipped_as_duplicates"] == 1


def test_run_sync_tasks_respects_current_run_only_policy(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other_dataset_id = "bluesky_00000000-0000-4000-8000-000000000002"
    config = minimal_sync_config()
    ingestion_params = config["ingestion_params"]
    ingestion_params["dedupe_policy"] = ["current_run"]
    sync_tasks = sync_bluesky.build_sync_tasks(ingestion_params)
    other_storage = BlueskyStorageManager(StorageStage.RAW, other_dataset_id)
    other_run = other_storage.create_new_run_dir("2026_05_29-10:00:00")
    other_storage.append_records(
        [
            make_ingestion_row(
                uri="at://did:plc:ex/app.bsky.feed.post/old",
                url="https://bsky.app/profile/user/post/old",
                author_handle="user",
                text="old",
            )
        ],
        other_run,
    )

    storage = BlueskyStorageManager(StorageStage.RAW, VALID_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_bluesky.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )

    def fake_search(
        client: Any,
        fetch_cfg: dict[str, Any],
        query: str,
        *,
        page_limit: int,
        cursor: str | None = None,
    ):
        return mock_search_response([mock_post("at://did:plc:ex/app.bsky.feed.post/old")])

    monkeypatch.setattr(sync_bluesky, "_search_posts_page", fake_search)

    sync_bluesky.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        storage,
        metadata,
        sync_tasks[:1],
        filename=storage.records_filename,
    )

    assert storage.load_seen_uris(run_dir) == {"at://did:plc:ex/app.bsky.feed.post/old"}
    assert metadata.get("posts_skipped_as_duplicates", 0) == 0


def test_run_sync_tasks_dedupes_within_run(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = minimal_sync_config()
    ingestion_params = config["ingestion_params"]
    sync_tasks = sync_bluesky.build_sync_tasks(ingestion_params)
    storage = BlueskyStorageManager(StorageStage.RAW, VALID_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_bluesky.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )
    duplicate_uri = "at://did:plc:ex/app.bsky.feed.post/dup"

    def fake_search(
        client: Any,
        fetch_cfg: dict[str, Any],
        query: str,
        *,
        page_limit: int,
        cursor: str | None = None,
    ):
        return mock_search_response([mock_post(duplicate_uri)])

    monkeypatch.setattr(sync_bluesky, "_search_posts_page", fake_search)

    sync_bluesky.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        storage,
        metadata,
        sync_tasks,
        filename=storage.records_filename,
    )

    assert storage.load_seen_uris(run_dir) == {duplicate_uri}
    assert metadata["row_count"] == 1


def test_resume_skips_completed_tasks(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = minimal_sync_config()
    ingestion_params = config["ingestion_params"]
    sync_tasks = sync_bluesky.build_sync_tasks(ingestion_params)
    storage = BlueskyStorageManager(StorageStage.RAW, VALID_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_bluesky.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )
    metadata["tasks"]["alpha"]["status"] = "completed"
    metadata["tasks"]["alpha"]["rows_collected"] = 1
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
    sync_bluesky.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        storage,
        resumed_metadata,
        sync_tasks,
        filename=storage.records_filename,
    )

    assert calls == ["beta"]
    assert resumed_metadata["tasks"]["beta"]["status"] == "completed"
    assert resumed_metadata["row_count"] == 2


def test_resume_dedupes_against_records_from_completed_tasks(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = minimal_sync_config()
    ingestion_params = config["ingestion_params"]
    sync_tasks = sync_bluesky.build_sync_tasks(ingestion_params)
    storage = BlueskyStorageManager(StorageStage.RAW, VALID_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_bluesky.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )

    already_seen_uri = "at://did:plc:ex/app.bsky.feed.post/a1"
    metadata["tasks"]["alpha"]["status"] = "completed"
    metadata["tasks"]["alpha"]["rows_collected"] = 1
    storage.append_records(
        [
            make_ingestion_row(
                uri=already_seen_uri,
                url="https://bsky.app/profile/user/post/a1",
                author_handle="user",
                text="x",
            )
        ],
        run_dir,
    )
    metadata["row_count"] = 1
    storage.write_run_metadata_atomic(run_dir, metadata)

    def fake_search(
        client: Any,
        fetch_cfg: dict[str, Any],
        query: str,
        *,
        page_limit: int,
        cursor: str | None = None,
    ):
        return mock_search_response(
            [
                mock_post(already_seen_uri),
                mock_post("at://did:plc:ex/app.bsky.feed.post/b1"),
            ]
        )

    monkeypatch.setattr(sync_bluesky, "_search_posts_page", fake_search)

    resumed_metadata = storage.load_run_metadata(run_dir)
    sync_bluesky.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        storage,
        resumed_metadata,
        sync_tasks,
        filename=storage.records_filename,
    )

    assert storage.load_seen_uris(run_dir) == {
        already_seen_uri,
        "at://did:plc:ex/app.bsky.feed.post/b1",
    }
    assert resumed_metadata["posts_skipped_as_duplicates"] == 1
    assert resumed_metadata["row_count"] == 2


def test_resume_legacy_keywords_metadata_raises_key_error() -> None:
    config = minimal_sync_config()
    sync_tasks = sync_bluesky.build_sync_tasks(config["ingestion_params"])
    legacy_metadata = {
        "sync_status": "in_progress",
        "keywords": {"alpha": {"status": "pending"}},
    }
    with pytest.raises(KeyError):
        validate_tasks_for_resume(sync_tasks, legacy_metadata, entity_label="keywords")
