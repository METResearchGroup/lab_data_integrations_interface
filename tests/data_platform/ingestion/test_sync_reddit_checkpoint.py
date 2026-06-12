from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from data_platform.ingestion import sync_reddit
from data_platform.utils.storage import RedditStorageManager, StorageStage
from tests.data_platform.constants import VALID_REDDIT_DATASET_ID
from tests.data_platform.ingestion.reddit_conftest import (
    minimal_reddit_sync_config,
    mock_comment_row,
    mock_post_row,
)


def test_init_sync_metadata_subreddit_task_ledger() -> None:
    config = minimal_reddit_sync_config()
    sync_tasks = sync_reddit.build_sync_tasks(config["ingestion_params"])
    metadata = sync_reddit.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )
    assert metadata["sync_status"] == "in_progress"
    assert set(metadata["tasks"]) == {"alphasub", "betasub"}
    assert metadata["tasks"]["alphasub"]["status"] == "pending"
    assert metadata["tasks"]["alphasub"]["kind"] == "reddit"


def test_run_sync_tasks_appends_per_subreddit(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = minimal_reddit_sync_config()
    ingestion_params = config["ingestion_params"]
    sync_tasks = sync_reddit.build_sync_tasks(ingestion_params)
    comment_storage = RedditStorageManager(StorageStage.RAW, VALID_REDDIT_DATASET_ID)
    post_storage = comment_storage.post_storage()
    run_dir = comment_storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_reddit.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )

    rows_by_subreddit = {
        "AlphaSub": (
            [mock_post_row("t3_post_a1", subreddit="alphasub")],
            [mock_comment_row("t1_comment_a1", subreddit="alphasub")],
        ),
        "BetaSub": (
            [mock_post_row("t3_post_b1", subreddit="betasub")],
            [mock_comment_row("t1_comment_b1", subreddit="betasub")],
        ),
    }

    def fake_fetch(
        reddit: Any,
        fetch_cfg: dict[str, Any],
        subreddit: str,
        *,
        sync_timestamp: str,
        include_posts: bool,
        include_comments: bool,
    ):
        post_rows, comment_rows = rows_by_subreddit[subreddit]
        stats = {
            "subreddit": subreddit,
            "listing": fetch_cfg.get("listing", "hot"),
            "limit_per_subreddit": fetch_cfg["limit_per_subreddit"],
            "posts_collected": len(post_rows),
            "comments_collected": len(comment_rows),
        }
        return post_rows, comment_rows, stats

    monkeypatch.setattr(sync_reddit, "fetch_records_for_subreddit", fake_fetch)

    sync_reddit.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        comment_storage,
        post_storage,
        metadata,
        sync_tasks,
        include_comments=True,
        include_posts=True,
    )

    assert metadata["tasks"]["alphasub"]["status"] == "completed"
    assert metadata["tasks"]["betasub"]["status"] == "completed"
    assert metadata["row_count"] == 2
    assert metadata["post_row_count"] == 2
    assert metadata["sync_status"] == "completed"
    assert len(comment_storage.load_seen_ids(run_dir, "comment_fullname")) == 2


def test_run_sync_tasks_skips_prior_run_comments(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = minimal_reddit_sync_config()
    ingestion_params = config["ingestion_params"]
    ingestion_params["dedupe_comments_from_prior_raw_runs"] = True
    ingestion_params["dedupe_across_datasets"] = False
    sync_tasks = sync_reddit.build_sync_tasks(ingestion_params)
    comment_storage = RedditStorageManager(StorageStage.RAW, VALID_REDDIT_DATASET_ID)
    post_storage = comment_storage.post_storage()

    prior_run = comment_storage.create_new_run_dir("2026_05_29-10:00:00")
    comment_storage.append_records(
        [mock_comment_row("t1_comment_old", subreddit="alphasub")],
        prior_run,
    )

    run_dir = comment_storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_reddit.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )

    def fake_fetch(
        reddit: Any,
        fetch_cfg: dict[str, Any],
        subreddit: str,
        *,
        sync_timestamp: str,
        include_posts: bool,
        include_comments: bool,
    ):
        return (
            [mock_post_row("t3_post_a1", subreddit="alphasub")],
            [
                mock_comment_row("t1_comment_old", subreddit="alphasub"),
                mock_comment_row("t1_comment_new", subreddit="alphasub"),
            ],
            {
                "subreddit": subreddit,
                "listing": fetch_cfg.get("listing", "hot"),
                "limit_per_subreddit": fetch_cfg["limit_per_subreddit"],
                "posts_collected": 1,
                "comments_collected": 2,
            },
        )

    monkeypatch.setattr(sync_reddit, "fetch_records_for_subreddit", fake_fetch)

    sync_reddit.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        comment_storage,
        post_storage,
        metadata,
        sync_tasks[:1],
        include_comments=True,
        include_posts=True,
    )

    seen = comment_storage.load_seen_ids(run_dir, "comment_fullname")
    assert seen == {"t1_comment_new"}
    assert metadata["comments_skipped_as_duplicates"] == 1


def test_run_sync_tasks_skips_ids_from_other_dataset(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other_dataset_id = "reddit_00000000-0000-4000-8000-000000000002"
    config = minimal_reddit_sync_config()
    ingestion_params = config["ingestion_params"]
    sync_tasks = sync_reddit.build_sync_tasks(ingestion_params)
    other_storage = RedditStorageManager(StorageStage.RAW, other_dataset_id)
    other_run = other_storage.create_new_run_dir("2026_05_29-10:00:00")
    other_storage.append_records(
        [mock_comment_row("t1_comment_old", subreddit="alphasub")],
        other_run,
    )

    comment_storage = RedditStorageManager(StorageStage.RAW, VALID_REDDIT_DATASET_ID)
    post_storage = comment_storage.post_storage()
    run_dir = comment_storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_reddit.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )

    def fake_fetch(
        reddit: Any,
        fetch_cfg: dict[str, Any],
        subreddit: str,
        *,
        sync_timestamp: str,
        include_posts: bool,
        include_comments: bool,
    ):
        return (
            [mock_post_row("t3_post_a1", subreddit="alphasub")],
            [
                mock_comment_row("t1_comment_old", subreddit="alphasub"),
                mock_comment_row("t1_comment_new", subreddit="alphasub"),
            ],
            {
                "subreddit": subreddit,
                "listing": fetch_cfg.get("listing", "hot"),
                "limit_per_subreddit": fetch_cfg["limit_per_subreddit"],
                "posts_collected": 1,
                "comments_collected": 2,
            },
        )

    monkeypatch.setattr(sync_reddit, "fetch_records_for_subreddit", fake_fetch)

    sync_reddit.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        comment_storage,
        post_storage,
        metadata,
        sync_tasks[:1],
        include_comments=True,
        include_posts=True,
    )

    seen = comment_storage.load_seen_ids(run_dir, "comment_fullname")
    assert seen == {"t1_comment_new"}
    assert metadata["comments_skipped_as_duplicates"] == 1


def test_run_sync_tasks_respects_dedupe_across_datasets_false(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other_dataset_id = "reddit_00000000-0000-4000-8000-000000000002"
    config = minimal_reddit_sync_config()
    ingestion_params = config["ingestion_params"]
    ingestion_params["dedupe_across_datasets"] = False
    sync_tasks = sync_reddit.build_sync_tasks(ingestion_params)
    other_storage = RedditStorageManager(StorageStage.RAW, other_dataset_id)
    other_run = other_storage.create_new_run_dir("2026_05_29-10:00:00")
    other_storage.append_records(
        [mock_comment_row("t1_comment_old", subreddit="alphasub")],
        other_run,
    )

    comment_storage = RedditStorageManager(StorageStage.RAW, VALID_REDDIT_DATASET_ID)
    post_storage = comment_storage.post_storage()
    run_dir = comment_storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_reddit.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )

    def fake_fetch(
        reddit: Any,
        fetch_cfg: dict[str, Any],
        subreddit: str,
        *,
        sync_timestamp: str,
        include_posts: bool,
        include_comments: bool,
    ):
        return (
            [mock_post_row("t3_post_a1", subreddit="alphasub")],
            [mock_comment_row("t1_comment_old", subreddit="alphasub")],
            {
                "subreddit": subreddit,
                "listing": fetch_cfg.get("listing", "hot"),
                "limit_per_subreddit": fetch_cfg["limit_per_subreddit"],
                "posts_collected": 1,
                "comments_collected": 1,
            },
        )

    monkeypatch.setattr(sync_reddit, "fetch_records_for_subreddit", fake_fetch)

    sync_reddit.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        comment_storage,
        post_storage,
        metadata,
        sync_tasks[:1],
        include_comments=True,
        include_posts=True,
    )

    seen = comment_storage.load_seen_ids(run_dir, "comment_fullname")
    assert seen == {"t1_comment_old"}
    assert metadata.get("comments_skipped_as_duplicates", 0) == 0


def test_resume_skips_completed_subreddits(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = minimal_reddit_sync_config()
    ingestion_params = config["ingestion_params"]
    sync_tasks = sync_reddit.build_sync_tasks(ingestion_params)
    comment_storage = RedditStorageManager(StorageStage.RAW, VALID_REDDIT_DATASET_ID)
    post_storage = comment_storage.post_storage()
    run_dir = comment_storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_reddit.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        sync_tasks,
    )
    metadata["tasks"]["alphasub"]["status"] = "completed"
    metadata["tasks"]["alphasub"]["comments_collected"] = 1
    comment_storage.append_records(
        [mock_comment_row("t1_comment_a1", subreddit="alphasub")],
        run_dir,
    )
    metadata["row_count"] = 1
    comment_storage.write_run_metadata_atomic(run_dir, metadata)

    calls: list[str] = []

    def fake_fetch(
        reddit: Any,
        fetch_cfg: dict[str, Any],
        subreddit: str,
        *,
        sync_timestamp: str,
        include_posts: bool,
        include_comments: bool,
    ):
        calls.append(subreddit)
        return (
            [mock_post_row("t3_post_b1", subreddit="betasub")],
            [mock_comment_row("t1_comment_b1", subreddit="betasub")],
            {
                "subreddit": subreddit,
                "listing": "hot",
                "limit_per_subreddit": 2,
                "posts_collected": 1,
                "comments_collected": 1,
            },
        )

    monkeypatch.setattr(sync_reddit, "fetch_records_for_subreddit", fake_fetch)

    resumed_metadata = comment_storage.load_run_metadata(run_dir)
    sync_reddit.run_sync_tasks(
        MagicMock(),
        ingestion_params,
        run_dir,
        comment_storage,
        post_storage,
        resumed_metadata,
        sync_tasks,
        include_comments=True,
        include_posts=True,
    )

    assert calls == ["BetaSub"]
    assert resumed_metadata["tasks"]["betasub"]["status"] == "completed"
    assert resumed_metadata["row_count"] == 2
