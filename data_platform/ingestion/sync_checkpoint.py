"""Shared checkpoint helpers for ingestion sync scripts."""

from __future__ import annotations

from enum import StrEnum
from collections.abc import Sequence
from typing import Any, Protocol


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SyncStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


TASKS_KEY = "tasks"


class HasTaskId(Protocol):
    @property
    def task_id(self) -> str: ...


def get_task_progress(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return metadata[TASKS_KEY]


def validate_tasks_for_resume(
    tasks: Sequence[HasTaskId],
    metadata: dict[str, Any],
    *,
    entity_label: str,
) -> None:
    progress = get_task_progress(metadata)
    task_ids = {task.task_id for task in tasks}
    metadata_ids = set(progress)
    missing = task_ids - metadata_ids
    extra = metadata_ids - task_ids
    if missing or extra:
        raise ValueError(
            f"Config {entity_label} do not match resume metadata "
            f"(missing in metadata: {sorted(missing)}, extra in metadata: {sorted(extra)})"
        )


def mark_remaining_tasks_skipped(progress: dict[str, dict[str, Any]]) -> None:
    for entry in progress.values():
        if entry["status"] == TaskStatus.PENDING.value:
            entry["status"] = TaskStatus.SKIPPED.value


def sync_status_from_tasks(progress: dict[str, dict[str, Any]]) -> SyncStatus:
    statuses = {entry["status"] for entry in progress.values()}
    unfinished = statuses - {TaskStatus.COMPLETED.value, TaskStatus.SKIPPED.value}
    return SyncStatus.COMPLETED if not unfinished else SyncStatus.IN_PROGRESS
