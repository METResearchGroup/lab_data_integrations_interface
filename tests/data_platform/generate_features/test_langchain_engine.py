from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from data_platform.generate_features.engines.langchain_engine import LangChainBatchEngine
from data_platform.generate_features.models import FeatureRunConfig, FeatureSpec, LabelTask
from tests.data_platform.constants import URI_POST_A, URI_POST_B


class _LlmOut(BaseModel):
    score: bool


class _RowModel(BaseModel):
    uri: str
    label_timestamp: str
    score: bool


def test_langchain_batch_engine_writes_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_chain = MagicMock()
    mock_chain.batch.return_value = [_LlmOut(score=True), _LlmOut(score=False)]

    monkeypatch.setattr(
        "data_platform.generate_features.engines.langchain_engine.build_structured_chat_chain",
        lambda **kwargs: mock_chain,
    )

    spec = FeatureSpec(
        name="test_feature",
        model=_RowModel,
        engine_type="langchain",
        generate_fn=lambda uri, text: _RowModel(uri=uri, label_timestamp="t", score=True),
        system_prompt="test",
        llm_output_schema=_LlmOut,
    )
    engine = LangChainBatchEngine(spec, FeatureRunConfig(max_concurrency=2))
    tasks = [
        LabelTask(uri=URI_POST_A, text="one"),
        LabelTask(uri=URI_POST_B, text="two"),
    ]
    labels = engine.batch_label_records(tasks)
    assert len(labels) == 2
    assert labels[0]["uri"] == URI_POST_A
    assert "label_timestamp" in labels[0]
