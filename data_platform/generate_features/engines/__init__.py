"""Batch execution engine factory."""

from __future__ import annotations

from data_platform.generate_features.engines.base import BatchExecutionEngine
from data_platform.generate_features.engines.langchain_engine import LangChainBatchEngine
from data_platform.generate_features.engines.thread_pool_engine import ThreadPoolBatchEngine
from data_platform.generate_features.models import FeatureRunConfig, FeatureSpec


def build_engine(spec: FeatureSpec, run_config: FeatureRunConfig) -> BatchExecutionEngine:
    if spec.engine_type == "langchain":
        return LangChainBatchEngine(spec, run_config)
    if spec.engine_type == "thread_pool":
        return ThreadPoolBatchEngine(spec, run_config)
    raise ValueError(f"Unknown engine_type: {spec.engine_type}")
