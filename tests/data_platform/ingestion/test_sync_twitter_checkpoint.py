from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from data_platform.ingestion import sync_twitter
from data_platform.utils.storage import StorageStage, TwitterStorageManager
from tests.data_platform.constants import VALID_TWITTER_DATASET_ID
from tests.data_platform.ingestion.twitter_conftest import mock_tweet_row


def _minimal_twitter_sync_config() -> dict[str, Any]:
    return {
        "dataset_id": VALID_TWITTER_DATASET_ID,
        "name": "test",
        "description": "test",
        "date": "2026-05-31",
        "record_types": ["twitter.tweet"],
        "ingestion_params": {
            "dedupe_policy": ["current_run", "prior_runs_all_datasets"],
            "keyword": ["alpha", "beta"],
            "limit_per_keyword": 2,
            "lang": "en",
            "exclude": ["reply", "retweet", "quote"],
        },
    }


def test_init_sync_metadata_task_ledger() -> None:
    config = _minimal_twitter_sync_config()
    sync_tasks = sync_twitter.build_sync_tasks(config["ingestion_params"])
    metadata = sync_twitter.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )
    assert metadata["sync_status"] == "in_progress"
    assert set(metadata["tasks"]) == {"alpha", "beta"}
    assert metadata["tasks"]["alpha"]["status"] == "pending"
    assert metadata["tasks"]["alpha"]["kind"] == "twitter"


def test_run_sync_tasks_appends_per_keyword(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _minimal_twitter_sync_config()
    ingestion_params = config["ingestion_params"]
    sync_tasks = sync_twitter.build_sync_tasks(ingestion_params)
    storage = TwitterStorageManager(StorageStage.RAW, VALID_TWITTER_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_twitter.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )

    rows_by_keyword = {
        "alpha": [mock_tweet_row("1000000000000000001", keyword="alpha")],
        "beta": [mock_tweet_row("1000000000000000002", keyword="beta")],
    }

    def fake_fetch(
        client: Any,
        keyword: str,
        *,
        limit: int,
        lang: str,
        exclude: list[str],
        sync_timestamp: str,
    ):
        rows = rows_by_keyword[keyword]
        return rows, {
            "pages_fetched": 1,
            "rows_collected": len(rows),
        }

    monkeypatch.setattr(sync_twitter, "fetch_posts_for_keyword", fake_fetch)

    sync_twitter.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        storage,
        metadata,
        sync_tasks,
        sync_timestamp="2026_05_30-10:00:00",
        csv_filename=sync_twitter.POSTS_CSV,
    )

    assert metadata["tasks"]["alpha"]["status"] == "completed"
    assert metadata["tasks"]["beta"]["status"] == "completed"
    assert metadata["row_count"] == 2
    assert metadata["sync_status"] == "completed"
    assert storage.load_seen_tweet_ids(run_dir) == {
        "1000000000000000001",
        "1000000000000000002",
    }


def test_run_sync_tasks_skips_prior_run_tweets_when_enabled(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _minimal_twitter_sync_config()
    ingestion_params = config["ingestion_params"]
    ingestion_params["dedupe_policy"] = ["current_run", "prior_runs_same_dataset"]
    sync_tasks = sync_twitter.build_sync_tasks(ingestion_params)
    storage = TwitterStorageManager(StorageStage.RAW, VALID_TWITTER_DATASET_ID)

    prior_run = storage.create_new_run_dir("2026_05_29-10:00:00")
    storage.append_records(
        [mock_tweet_row("1000000000000000000", keyword="alpha")],
        prior_run,
    )

    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_twitter.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )

    def fake_fetch(
        client: Any,
        keyword: str,
        *,
        limit: int,
        lang: str,
        exclude: list[str],
        sync_timestamp: str,
    ):
        return (
            [
                mock_tweet_row("1000000000000000000", keyword=keyword),
                mock_tweet_row("1000000000000000001", keyword=keyword),
            ],
            {"pages_fetched": 1, "rows_collected": 2},
        )

    monkeypatch.setattr(sync_twitter, "fetch_posts_for_keyword", fake_fetch)
    monkeypatch.setattr(storage, "load_seen_ids_from_athena", lambda: {"1000000000000000000"})

    sync_twitter.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        storage,
        metadata,
        sync_tasks[:1],
        sync_timestamp="2026_05_30-10:00:00",
        csv_filename=sync_twitter.POSTS_CSV,
    )

    assert storage.load_seen_tweet_ids(run_dir) == {"1000000000000000001"}
    assert metadata["tweets_skipped_as_duplicates"] == 1


def test_run_sync_tasks_does_not_skip_prior_runs_when_disabled(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _minimal_twitter_sync_config()
    ingestion_params = config["ingestion_params"]
    ingestion_params["dedupe_policy"] = ["current_run"]
    sync_tasks = sync_twitter.build_sync_tasks(ingestion_params)
    storage = TwitterStorageManager(StorageStage.RAW, VALID_TWITTER_DATASET_ID)

    prior_run = storage.create_new_run_dir("2026_05_29-10:00:00")
    storage.append_records(
        [mock_tweet_row("1000000000000000000", keyword="alpha")],
        prior_run,
    )

    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_twitter.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )

    def fake_fetch(
        client: Any,
        keyword: str,
        *,
        limit: int,
        lang: str,
        exclude: list[str],
        sync_timestamp: str,
    ):
        return (
            [
                mock_tweet_row("1000000000000000000", keyword=keyword),
                mock_tweet_row("1000000000000000001", keyword=keyword),
            ],
            {"pages_fetched": 1, "rows_collected": 2},
        )

    monkeypatch.setattr(sync_twitter, "fetch_posts_for_keyword", fake_fetch)

    sync_twitter.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        storage,
        metadata,
        sync_tasks[:1],
        sync_timestamp="2026_05_30-10:00:00",
        csv_filename=sync_twitter.POSTS_CSV,
    )

    assert storage.load_seen_tweet_ids(run_dir) == {
        "1000000000000000000",
        "1000000000000000001",
    }
    assert metadata.get("tweets_skipped_as_duplicates", 0) == 0


def test_run_sync_tasks_skips_ids_from_other_dataset(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other_dataset_id = "twitter_00000000-0000-4000-8000-000000000002"
    config = _minimal_twitter_sync_config()
    ingestion_params = config["ingestion_params"]
    sync_tasks = sync_twitter.build_sync_tasks(ingestion_params)
    other_storage = TwitterStorageManager(StorageStage.RAW, other_dataset_id)
    other_run = other_storage.create_new_run_dir("2026_05_29-10:00:00")
    other_storage.append_records(
        [mock_tweet_row("1000000000000000000", keyword="alpha")],
        other_run,
    )

    storage = TwitterStorageManager(StorageStage.RAW, VALID_TWITTER_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_twitter.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )

    def fake_fetch(
        client: Any,
        keyword: str,
        *,
        limit: int,
        lang: str,
        exclude: list[str],
        sync_timestamp: str,
    ):
        return (
            [
                mock_tweet_row("1000000000000000000", keyword=keyword),
                mock_tweet_row("1000000000000000001", keyword=keyword),
            ],
            {"pages_fetched": 1, "rows_collected": 2},
        )

    monkeypatch.setattr(sync_twitter, "fetch_posts_for_keyword", fake_fetch)
    monkeypatch.setattr(storage, "load_seen_ids_from_athena", lambda: {"1000000000000000000"})

    sync_twitter.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        storage,
        metadata,
        sync_tasks[:1],
        sync_timestamp="2026_05_30-10:00:00",
        csv_filename=sync_twitter.POSTS_CSV,
    )

    assert storage.load_seen_tweet_ids(run_dir) == {"1000000000000000001"}
    assert metadata["tweets_skipped_as_duplicates"] == 1


def test_run_sync_tasks_respects_current_run_only_policy(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other_dataset_id = "twitter_00000000-0000-4000-8000-000000000002"
    config = _minimal_twitter_sync_config()
    ingestion_params = config["ingestion_params"]
    ingestion_params["dedupe_policy"] = ["current_run"]
    sync_tasks = sync_twitter.build_sync_tasks(ingestion_params)
    other_storage = TwitterStorageManager(StorageStage.RAW, other_dataset_id)
    other_run = other_storage.create_new_run_dir("2026_05_29-10:00:00")
    other_storage.append_records(
        [mock_tweet_row("1000000000000000000", keyword="alpha")],
        other_run,
    )

    storage = TwitterStorageManager(StorageStage.RAW, VALID_TWITTER_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_twitter.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )

    def fake_fetch(
        client: Any,
        keyword: str,
        *,
        limit: int,
        lang: str,
        exclude: list[str],
        sync_timestamp: str,
    ):
        return (
            [mock_tweet_row("1000000000000000000", keyword=keyword)],
            {"pages_fetched": 1, "rows_collected": 1},
        )

    monkeypatch.setattr(sync_twitter, "fetch_posts_for_keyword", fake_fetch)

    sync_twitter.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        storage,
        metadata,
        sync_tasks[:1],
        sync_timestamp="2026_05_30-10:00:00",
        csv_filename=sync_twitter.POSTS_CSV,
    )

    assert storage.load_seen_tweet_ids(run_dir) == {"1000000000000000000"}
    assert metadata.get("tweets_skipped_as_duplicates", 0) == 0


def test_resume_skips_completed_tasks(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _minimal_twitter_sync_config()
    ingestion_params = config["ingestion_params"]
    sync_tasks = sync_twitter.build_sync_tasks(ingestion_params)
    storage = TwitterStorageManager(StorageStage.RAW, VALID_TWITTER_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_twitter.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )
    metadata["tasks"]["alpha"]["status"] = "completed"
    metadata["tasks"]["alpha"]["rows_collected"] = 1
    storage.append_records(
        [mock_tweet_row("1000000000000000001", keyword="alpha")],
        run_dir,
    )
    metadata["row_count"] = 1
    storage.write_run_metadata_atomic(run_dir, metadata)

    calls: list[str] = []

    def fake_fetch(
        client: Any,
        keyword: str,
        *,
        limit: int,
        lang: str,
        exclude: list[str],
        sync_timestamp: str,
    ):
        calls.append(keyword)
        return (
            [mock_tweet_row("1000000000000000002", keyword=keyword)],
            {"pages_fetched": 1, "rows_collected": 1},
        )

    monkeypatch.setattr(sync_twitter, "fetch_posts_for_keyword", fake_fetch)

    resumed_metadata = storage.load_run_metadata(run_dir)
    sync_twitter.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        storage,
        resumed_metadata,
        sync_tasks,
        sync_timestamp="2026_05_30-10:00:00",
        csv_filename=sync_twitter.POSTS_CSV,
    )

    assert calls == ["beta"]
    assert resumed_metadata["tasks"]["beta"]["status"] == "completed"
    assert resumed_metadata["row_count"] == 2
