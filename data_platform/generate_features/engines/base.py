"""BatchExecutionEngine protocol and shared label_records loop."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from collector.retry import retry_llm_completion
from data_platform.generate_features.deadletter import append_deadletter_batch
from data_platform.generate_features.models import (
    BatchRunStats,
    FeatureRunConfig,
    FeatureSpec,
    LabelTask,
)
from data_platform.utils.storage import StorageManager
from lib.timestamp_utils import get_current_timestamp


class BatchExecutionEngine(Protocol):
    spec: FeatureSpec
    run_config: FeatureRunConfig

    def batch_label_records(self, tasks: list[LabelTask]) -> list[dict]: ...

    def batch_write_records(
        self,
        labels: list[dict],
        *,
        feature_name: str,
        features_dir: Path,
    ) -> None: ...

    def label_records(
        self,
        tasks: list[LabelTask],
        *,
        feature_name: str,
        features_dir: Path,
        batch_size: int,
        on_batch_complete: Callable[[int, int], None],
    ) -> BatchRunStats: ...


def load_seen_uris_from_features_dir(features_dir: Path, feature_name: str) -> set[str]:
    storage = StorageManager(
        "bluesky",
        "features",
        BaseModel,
        "",
        records_filename=f"{feature_name}.csv",
    )
    return storage.load_seen_uris(features_dir, filename=f"{feature_name}.csv")


def filter_seen_tasks(
    tasks: list[LabelTask],
    features_dir: Path,
    feature_name: str,
) -> list[LabelTask]:
    seen = load_seen_uris_from_features_dir(features_dir, feature_name)
    if not seen:
        return tasks
    return [task for task in tasks if task.uri not in seen]


def batched(tasks: list[LabelTask], batch_size: int) -> Iterator[list[LabelTask]]:
    for i in range(0, len(tasks), batch_size):
        yield tasks[i : i + batch_size]


class BaseBatchExecutionEngine:
    def __init__(self, spec: FeatureSpec, run_config: FeatureRunConfig) -> None:
        self.spec = spec
        self.run_config = run_config

    def batch_label_records(self, tasks: list[LabelTask]) -> list[dict]:
        raise NotImplementedError

    def batch_write_records(
        self,
        labels: list[dict],
        *,
        feature_name: str,
        features_dir: Path,
    ) -> None:
        if not labels:
            return
        storage = StorageManager(
            "bluesky",
            "features",
            self.spec.model,
            "",
            records_filename=f"{feature_name}.csv",
        )
        storage.append_records(labels, features_dir, filename=f"{feature_name}.csv")

    def label_records(
        self,
        tasks: list[LabelTask],
        *,
        feature_name: str,
        features_dir: Path,
        batch_size: int,
        on_batch_complete: Callable[[int, int], None],
    ) -> BatchRunStats:
        stats = BatchRunStats()
        max_retries = self.run_config.max_label_retries

        @retry_llm_completion(max_retries=max_retries)
        def _batch_with_retry(chunk: list[LabelTask]) -> list[dict]:
            return self.batch_label_records(chunk)

        for batch_index, chunk in enumerate(batched(tasks, batch_size)):
            pending = filter_seen_tasks(chunk, features_dir, feature_name)
            if not pending:
                continue

            uris = [task.uri for task in pending]
            try:
                labels = _batch_with_retry(pending)
            except Exception as exc:
                append_deadletter_batch(
                    features_dir,
                    feature=feature_name,
                    uris=uris,
                    error=f"{type(exc).__name__}: {exc}",
                    attempts=max_retries + 1,
                    batch_index=batch_index,
                )
                stats.failed_batches += 1
                on_batch_complete(0, 1)
                continue

            self.batch_write_records(
                labels,
                feature_name=feature_name,
                features_dir=features_dir,
            )
            stats.labeled += len(labels)
            on_batch_complete(len(labels), 0)

        return stats


def row_with_label_timestamp(row: dict, *, label_timestamp: str | None = None) -> dict:
    ts = label_timestamp or get_current_timestamp()
    return {**row, "label_timestamp": ts}
