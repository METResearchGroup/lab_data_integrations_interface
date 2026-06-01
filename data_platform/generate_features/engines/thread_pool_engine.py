"""ThreadPoolExecutor engine for non-LLM features (e.g. Perspective API)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from data_platform.generate_features.engines.base import (
    BaseBatchExecutionEngine,
    row_with_label_timestamp,
)
from data_platform.generate_features.models import LabelTask
from lib.timestamp_utils import get_current_timestamp


class ThreadPoolBatchEngine(BaseBatchExecutionEngine):
    """Label tasks by calling generate_fn concurrently in a thread pool."""

    def batch_label_records(self, tasks: list[LabelTask]) -> list[dict]:
        """Score each task with generate_fn and return validated label dict rows."""
        if not tasks:
            return []

        label_timestamp = get_current_timestamp()
        rows: list[dict] = []

        def _label_one(task: LabelTask) -> dict:
            result = self.spec.generate_fn(task.uri, task.text)
            return row_with_label_timestamp(
                result.model_dump(),
                label_timestamp=label_timestamp,
            )

        with ThreadPoolExecutor(max_workers=self.run_config.max_concurrency) as executor:
            for row in executor.map(_label_one, tasks):
                validated = self.spec.model.model_validate(row)
                rows.append(validated.model_dump())
        return rows
