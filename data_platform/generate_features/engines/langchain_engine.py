"""LangChain Runnable.batch engine for LLM feature labeling."""

from __future__ import annotations

from typing import cast

from langchain_core.runnables import RunnableConfig

from data_platform.generate_features.engines.base import (
    BaseBatchExecutionEngine,
    row_with_label_timestamp,
)
from data_platform.generate_features.models import FeatureRunConfig, FeatureSpec, LabelTask
from lib.timestamp_utils import get_current_timestamp
from ml_tooling.llm.llm import build_structured_chat_chain


class LangChainBatchEngine(BaseBatchExecutionEngine):
    """Label tasks via one structured-output chain and Runnable.batch concurrency."""

    def __init__(self, spec: FeatureSpec, run_config: FeatureRunConfig) -> None:
        super().__init__(spec, run_config)
        if spec.system_prompt is None or spec.llm_output_schema is None:
            raise ValueError(f"Feature {spec.name} requires system_prompt and llm_output_schema")
        self._chain = build_structured_chat_chain(
            output_schema=spec.llm_output_schema,
            system_prompt=spec.system_prompt,
        )
        self._label_timestamp = get_current_timestamp()

    def batch_label_records(self, tasks: list[LabelTask]) -> list[dict]:
        """Run chain.batch on pending tasks and return validated label dict rows."""
        if not tasks:
            return []

        inputs = [{"user_prompt": task.text} for task in tasks]
        results = cast(
            list,
            self._chain.batch(
                inputs,
                config=RunnableConfig(max_concurrency=self.run_config.max_concurrency),
            ),
        )

        rows: list[dict] = []
        for task, result in zip(tasks, results, strict=True):
            fields = result.model_dump() if hasattr(result, "model_dump") else dict(result)
            row = row_with_label_timestamp(
                {"uri": task.uri, **fields},
                label_timestamp=self._label_timestamp,
            )
            validated = self.spec.model.model_validate(row)
            rows.append(validated.model_dump())
        return rows
