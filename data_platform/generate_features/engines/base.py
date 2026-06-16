"""BatchExecutionEngine protocol and shared label_records loop."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from typing import Protocol

from tqdm import tqdm

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
    """Protocol for labeling tasks in atomic batches."""

    spec: FeatureSpec
    run_config: FeatureRunConfig

    def batch_label_records(self, tasks: list[LabelTask]) -> list[dict]: ...

    def batch_write_records(
        self,
        labels: list[dict],
        *,
        feature_storage: StorageManager,
    ) -> None: ...

    def label_records(
        self,
        tasks: list[LabelTask],
        *,
        feature_name: str,
        feature_storage: StorageManager,
        batch_size: int,
        on_batch_complete: Callable[[int, int], None],
    ) -> BatchRunStats: ...


def load_seen_uris_from_features_dir(feature_storage: StorageManager) -> set[str]:
    """Return URIs already present in the feature file under the features dir."""
    return feature_storage.load_seen_uris(feature_storage.root_dir)


def filter_seen_tasks(
    tasks: list[LabelTask],
    feature_storage: StorageManager,
) -> list[LabelTask]:
    """Drop tasks whose URI is already labeled in the on-disk feature file."""
    seen = load_seen_uris_from_features_dir(feature_storage)
    if not seen:
        return tasks
    return [task for task in tasks if task.uri not in seen]


def batched(tasks: list[LabelTask], batch_size: int) -> Iterator[list[LabelTask]]:
    """Yield consecutive chunks of at most batch_size tasks."""
    for i in range(0, len(tasks), batch_size):
        yield tasks[i : i + batch_size]


class BaseBatchExecutionEngine:
    """
    Shared batch loop: retry labeling, append rows via StorageManager,
    or record deadletter batches."""

    def __init__(self, spec: FeatureSpec, run_config: FeatureRunConfig) -> None:
        self.spec = spec
        self.run_config = run_config

    def batch_label_records(self, tasks: list[LabelTask]) -> list[dict]:
        raise NotImplementedError

    def batch_write_records(
        self,
        labels: list[dict],
        *,
        feature_storage: StorageManager,
    ) -> None:
        """Validate and append label rows via StorageManager."""
        if not labels:
            return
        feature_storage.append_records(labels, feature_storage.root_dir)

    def label_records(
        self,
        tasks: list[LabelTask],
        *,
        feature_name: str,
        feature_storage: StorageManager,
        batch_size: int,
        on_batch_complete: Callable[[int, int], None],
    ) -> BatchRunStats:
        """Label records using feature classifier.

        Steps:
        1. Batch inference (with retries). On failures here, add to deadletter.
        2. Write the labeled records to output.
        """
        stats = BatchRunStats()
        max_retries = self.run_config.max_label_retries

        @retry_llm_completion(max_retries=max_retries)
        def _batch_with_retry(chunk: list[LabelTask]) -> list[dict]:
            return self.batch_label_records(chunk)

        pbar = tqdm(
            total=len(tasks),
            desc=feature_name,
            unit="post",
            disable=not sys.stderr.isatty(),
        )
        try:
            for batch_index, chunk in enumerate(batched(tasks, batch_size)):
                pending = filter_seen_tasks(chunk, feature_storage)
                if not pending:
                    continue

                # Step 1: Run batch inference logic (with retry). If failed,
                # add to deadletter.
                uris = [task.uri for task in pending]
                try:
                    labels = _batch_with_retry(pending)
                except Exception as exc:
                    append_deadletter_batch(
                        feature_storage.root_dir,
                        feature=feature_name,
                        uris=uris,
                        error=f"{type(exc).__name__}: {exc}",
                        attempts=max_retries + 1,
                        batch_index=batch_index,
                    )
                    stats.failed_batches += 1
                    on_batch_complete(0, 1)
                    tqdm.write(
                        f"{feature_name}: batch {batch_index} failed "
                        f"({len(uris)} posts → deadletter)"
                    )
                    continue

                # Step 2: Write labeled records.
                self.batch_write_records(labels, feature_storage=feature_storage)
                stats.labeled += len(labels)
                pbar.update(len(labels))
                on_batch_complete(len(labels), 0)
        finally:
            pbar.close()

        return stats


def row_with_label_timestamp(row: dict, *, label_timestamp: str | None = None) -> dict:
    """Attach label_timestamp to a label row, defaulting to the current run timestamp."""
    ts = label_timestamp or get_current_timestamp()
    return {**row, "label_timestamp": ts}
