from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from data_platform.ingestion import sync_reddit
from data_platform.utils.storage import RedditStorageManager
from tests.data_platform.constants import VALID_REDDIT_DATASET_ID
from tests.data_platform.ingestion.reddit_conftest import (
    minimal_reddit_sync_config,
    mock_comment_row,
    mock_post_row,
)


def test_init_sync_metadata_subreddit_ledger() -> None:
    config = minimal_reddit_sync_config()
    work_items = sync_reddit.iter_fetch_work_items(config["fetch"])
    metadata = sync_reddit.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        work_items,
    )
    assert metadata["sync_status"] == "in_progress"
    assert set(metadata["subreddits"]) == {"alphasub", "betasub"}
    assert metadata["subreddits"]["alphasub"]["status"] == "pending"


def test_run_subreddit_sync_loop_appends_per_subreddit(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = minimal_reddit_sync_config()
    fetch = config["fetch"]
    work_items = sync_reddit.iter_fetch_work_items(fetch)
    comment_storage = RedditStorageManager("raw", VALID_REDDIT_DATASET_ID)
    post_storage = comment_storage.post_storage()
    run_dir = comment_storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_reddit.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        work_items,
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

    sync_reddit.run_subreddit_sync_loop(
        MagicMock(),
        fetch,
        run_dir,
        comment_storage,
        post_storage,
        metadata,
        work_items,
        include_comments=True,
        include_posts=True,
    )

    assert metadata["subreddits"]["alphasub"]["status"] == "completed"
    assert metadata["subreddits"]["betasub"]["status"] == "completed"
    assert metadata["row_count"] == 2
    assert metadata["post_row_count"] == 2
    assert metadata["sync_status"] == "completed"
    assert len(comment_storage.load_seen_ids(run_dir, "comment_fullname")) == 2


def test_resume_skips_completed_subreddits(
    data_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = minimal_reddit_sync_config()
    fetch = config["fetch"]
    work_items = sync_reddit.iter_fetch_work_items(fetch)
    comment_storage = RedditStorageManager("raw", VALID_REDDIT_DATASET_ID)
    post_storage = comment_storage.post_storage()
    run_dir = comment_storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = sync_reddit.init_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        work_items,
    )
    metadata["subreddits"]["alphasub"]["status"] = "completed"
    metadata["subreddits"]["alphasub"]["comments_collected"] = 1
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
    sync_reddit.run_subreddit_sync_loop(
        MagicMock(),
        fetch,
        run_dir,
        comment_storage,
        post_storage,
        resumed_metadata,
        work_items,
        include_comments=True,
        include_posts=True,
    )

    assert calls == ["BetaSub"]
    assert resumed_metadata["subreddits"]["betasub"]["status"] == "completed"
    assert resumed_metadata["row_count"] == 2
