from __future__ import annotations

from pydantic import BaseModel

from data_platform.generate_features.engines.thread_pool_engine import ThreadPoolBatchEngine
from data_platform.generate_features.models import FeatureRunConfig, FeatureSpec, LabelTask


class _RowModel(BaseModel):
    uri: str
    label_timestamp: str
    value: int


def test_thread_pool_batch_engine_labels_tasks() -> None:
    def generate_fn(uri: str, text: str) -> _RowModel:
        return _RowModel(uri=uri, label_timestamp="ignored", value=len(text))

    spec = FeatureSpec(
        name="test_feature",
        model=_RowModel,
        engine_type="thread_pool",
        generate_fn=generate_fn,
    )
    engine = ThreadPoolBatchEngine(spec, FeatureRunConfig(max_concurrency=2))
    tasks = [
        LabelTask(uri="at://a/post/1", text="hi"),
        LabelTask(uri="at://b/post/2", text="hey"),
    ]
    labels = engine.batch_label_records(tasks)
    assert len(labels) == 2
    assert labels[0]["value"] == 2
    assert labels[1]["value"] == 3
