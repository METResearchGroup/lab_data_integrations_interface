from __future__ import annotations

from dataclasses import dataclass

import pytest

from data_platform.ingestion.sync_checkpoint import (
    SyncStatus,
    TaskStatus,
    get_task_progress,
    mark_remaining_tasks_skipped,
    sync_status_from_tasks,
    validate_tasks_for_resume,
)


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
