from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from data_platform.ingestion.dedupe import append_deduped_rows
from data_platform.ingestion.sync_checkpoint import (
    SyncStatus,
    TaskStatus,
    build_base_sync_metadata,
    find_resume_run_dir,
    flush_run_metadata,
    get_task_progress,
    mark_remaining_tasks_skipped,
    mark_task_completed,
    parse_max_rows,
    record_type_to_filename,
    require_dataset_id,
    stop_at_max_rows,
    sync_status_from_tasks,
    validate_tasks_for_resume,
)
from data_platform.utils.storage import TwitterStorageManager
from tests.data_platform.constants import VALID_TWITTER_DATASET_ID
from tests.data_platform.ingestion.twitter_conftest import mock_tweet_row


@dataclass(frozen=True)
class _StubTask:
    task_id: str


def test_get_task_progress_missing_tasks_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_task_progress({})


def test_validate_tasks_for_resume_mismatch_raises_value_error() -> None:
    metadata = {
        "tasks": {
            "alpha": {"status": TaskStatus.PENDING.value},
            "extra": {"status": TaskStatus.PENDING.value},
        }
    }
    tasks = [_StubTask("alpha"), _StubTask("beta")]
    with pytest.raises(ValueError, match="missing in metadata"):
        validate_tasks_for_resume(tasks, metadata, entity_label="keywords")


def test_validate_tasks_for_resume_matching_tasks_passes() -> None:
    metadata = {
        "tasks": {
            "alpha": {"status": TaskStatus.PENDING.value},
            "beta": {"status": TaskStatus.PENDING.value},
        }
    }
    tasks = [_StubTask("alpha"), _StubTask("beta")]
    validate_tasks_for_resume(tasks, metadata, entity_label="keywords")


def test_mark_remaining_tasks_skipped() -> None:
    progress = {
        "a": {"status": TaskStatus.PENDING.value},
        "b": {"status": TaskStatus.COMPLETED.value},
        "c": {"status": TaskStatus.IN_PROGRESS.value},
    }
    mark_remaining_tasks_skipped(progress)
    assert progress["a"]["status"] == TaskStatus.SKIPPED.value
    assert progress["b"]["status"] == TaskStatus.COMPLETED.value
    assert progress["c"]["status"] == TaskStatus.IN_PROGRESS.value


def test_sync_status_from_tasks_all_done() -> None:
    progress = {
        "a": {"status": TaskStatus.COMPLETED.value},
        "b": {"status": TaskStatus.SKIPPED.value},
    }
    assert sync_status_from_tasks(progress) == SyncStatus.COMPLETED


def test_sync_status_from_tasks_still_in_progress() -> None:
    progress = {
        "a": {"status": TaskStatus.COMPLETED.value},
        "b": {"status": TaskStatus.PENDING.value},
    }
    assert sync_status_from_tasks(progress) == SyncStatus.IN_PROGRESS


def test_require_dataset_id_missing_raises() -> None:
    with pytest.raises(ValueError, match="dataset_id"):
        require_dataset_id({}, platform="twitter")


def test_record_type_to_filename_known_types() -> None:
    assert record_type_to_filename("app.bsky.feed.post") == "posts.csv"
    assert record_type_to_filename("reddit.comment") == "comments.csv"
    assert record_type_to_filename("custom.record") == "record.csv"


def test_parse_max_rows_none_when_unset() -> None:
    assert parse_max_rows({}) is None
    assert parse_max_rows({"max_rows": 100}) == 100


def test_build_base_sync_metadata_includes_tasks() -> None:
    config = {
        "dataset_id": VALID_TWITTER_DATASET_ID,
        "name": "test",
        "description": "desc",
        "date": "2026-05-31",
        "record_types": ["twitter.tweet"],
        "ingestion_params": {},
    }
    metadata = build_base_sync_metadata(
        config,
        Path("test.yaml"),
        "2026_05_30-10:00:00",
        [_StubTask("alpha")],
        task_progress_builder=lambda task: {"status": TaskStatus.PENDING.value, "id": task.task_id},
        extra_fields={"post_row_count": 0},
    )
    assert metadata["sync_status"] == SyncStatus.IN_PROGRESS.value
    assert metadata["tasks"]["alpha"]["status"] == TaskStatus.PENDING.value
    assert metadata["post_row_count"] == 0


def test_find_resume_run_dir_specific_run(data_root) -> None:
    storage = TwitterStorageManager("raw", VALID_TWITTER_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    flush_run_metadata(storage, run_dir, {"sync_status": SyncStatus.IN_PROGRESS.value, "tasks": {}})
    assert find_resume_run_dir(storage, run_dir_name="2026_05_30-10:00:00") == run_dir


def test_find_resume_run_dir_latest_in_progress(data_root) -> None:
    storage = TwitterStorageManager("raw", VALID_TWITTER_DATASET_ID)
    older = storage.create_new_run_dir("2026_05_30-09:00:00")
    newer = storage.create_new_run_dir("2026_05_30-10:00:00")
    flush_run_metadata(storage, older, {"sync_status": SyncStatus.COMPLETED.value, "tasks": {}})
    flush_run_metadata(storage, newer, {"sync_status": SyncStatus.IN_PROGRESS.value, "tasks": {}})
    assert find_resume_run_dir(storage, run_dir_name=None) == newer


def test_mark_task_completed_updates_entry_and_metadata(data_root) -> None:
    storage = TwitterStorageManager("raw", VALID_TWITTER_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = {"row_count": 0, "tasks": {"alpha": {"status": TaskStatus.PENDING.value}}}
    entry = metadata["tasks"]["alpha"]

    mark_task_completed(
        entry,
        storage,
        run_dir,
        metadata,
        entry_updates={"pages_fetched": 2, "rows_collected": 5},
        metadata_updates={"row_count": 5},
    )

    assert entry["status"] == TaskStatus.COMPLETED.value
    assert entry["last_error"] is None
    assert entry["pages_fetched"] == 2
    assert metadata["row_count"] == 5
    assert storage.load_run_metadata(run_dir)["tasks"]["alpha"]["status"] == TaskStatus.COMPLETED.value


def test_stop_at_max_rows_marks_pending_skipped(data_root) -> None:
    storage = TwitterStorageManager("raw", VALID_TWITTER_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    metadata = {
        "row_count": 10,
        "tasks": {
            "a": {"status": TaskStatus.PENDING.value},
            "b": {"status": TaskStatus.COMPLETED.value},
        },
    }
    assert stop_at_max_rows(metadata, storage, run_dir, 10) is True
    assert metadata["tasks"]["a"]["status"] == TaskStatus.SKIPPED.value


def test_append_deduped_rows_skips_seen_ids(data_root) -> None:
    storage = TwitterStorageManager("raw", VALID_TWITTER_DATASET_ID)
    run_dir = storage.create_new_run_dir("2026_05_30-10:00:00")
    existing = [mock_tweet_row("1")]
    storage.append_records(existing, run_dir)
    incoming = [mock_tweet_row("1"), mock_tweet_row("2")]
    new_rows, skipped = append_deduped_rows(
        storage,
        run_dir,
        incoming,
        "tweet_id",
        prior_ids=set(),
    )
    assert skipped == 1
    assert len(new_rows) == 1
    assert new_rows[0]["tweet_id"] == "2"
