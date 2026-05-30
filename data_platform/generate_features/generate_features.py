"""Generic feature-generation pipeline for preprocessed post records."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel
from tqdm import tqdm

from data_platform.utils.dataset import dataset_root, relative_run_path
from data_platform.utils.feature_labels import FeatureLabelQuery
from data_platform.utils.storage import StorageManager
from lib.timestamp_utils import get_current_timestamp
from ml_tooling.llm import opik as opik_telemetry

FeatureFn = Callable[[str, str], BaseModel]


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    generate_fn: FeatureFn
    model: type[BaseModel]


@dataclass(frozen=True)
class FeatureGenerationConfig:
    platform: str
    id_column: str
    text_column: str
    feature_registry: dict[str, FeatureSpec]
    input_storage: StorageManager
    output_run_storage: StorageManager
    feature_label_query: FeatureLabelQuery


def filter_records_needing_features(
    records: pd.DataFrame,
    feature_name: str,
    config: FeatureGenerationConfig,
) -> pd.DataFrame:
    """Return records that still need labels for feature_name."""
    return config.feature_label_query.filter_unlabeled(records, feature_name)


def run_feature_pipeline(
    records: pd.DataFrame,
    generate_fn: FeatureFn,
    *,
    feature_name: str,
    id_column: str,
    text_column: str,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Generate feature labels for each record."""
    if records.empty:
        return []

    rows: list[dict[str, Any]] = []
    for _, record in tqdm(
        records.iterrows(),
        total=len(records),
        desc=feature_name,
    ):
        record_id = str(record[id_column])
        token = opik_telemetry.push_context(
            feature_name=feature_name,
            uri=record_id,
            run_id=run_id,
        )
        try:
            result = generate_fn(record_id, str(record[text_column]))
        finally:
            opik_telemetry.pop_context(token)
        rows.append(result.model_dump())
    return rows


def save_feature_labels(
    platform: str,
    feature_name: str,
    rows: list[dict[str, Any]],
    model: type[BaseModel],
    run_dir: Path,
    dataset_id: str,
) -> Path:
    """Persist feature labels for one feature to the shared features run directory."""
    storage = StorageManager(
        platform,
        "features",
        model,
        dataset_id,
        records_filename=f"{feature_name}.csv",
    )
    return storage.write_records(rows, run_dir, filename=f"{feature_name}.csv")


def generate_and_export_feature_labels(
    records: pd.DataFrame,
    spec: FeatureSpec,
    config: FeatureGenerationConfig,
    output_run_dir: Path,
) -> tuple[Path, int]:
    """Generate labels for one feature and write them to the run directory."""
    candidates = filter_records_needing_features(records, spec.name, config)
    already_labeled = len(records) - len(candidates)
    labels = run_feature_pipeline(
        candidates,
        spec.generate_fn,
        feature_name=spec.name,
        id_column=config.id_column,
        text_column=config.text_column,
        run_id=str(output_run_dir),
    )
    csv_path = save_feature_labels(
        config.platform,
        spec.name,
        labels,
        spec.model,
        output_run_dir,
        config.output_run_storage.dataset_id,
    )
    print(
        f"generate_features: {spec.name} -> "
        f"{len(labels)} labels from {len(candidates)} candidate records "
        f"({already_labeled} already labeled)"
    )
    return csv_path, len(labels)


def generate_features(
    records: pd.DataFrame,
    config: FeatureGenerationConfig,
) -> dict[str, Path]:
    """Generate all configured features and write label CSVs."""
    if records.empty:
        print("generate_features: no records to label")
        return {}

    source_run_dir = config.input_storage.latest_run_dir()
    output_run_dir = config.output_run_storage.create_new_run_dir(get_current_timestamp())

    written: dict[str, Path] = {}
    counts: dict[str, int] = {}

    with opik_telemetry.project_scope():
        for feature_name, spec in config.feature_registry.items():
            csv_path, label_count = generate_and_export_feature_labels(
                records,
                spec,
                config,
                output_run_dir,
            )
            written[feature_name] = csv_path
            counts[feature_name] = label_count

        root = dataset_root(
            config.platform,
            config.input_storage.dataset_id,
        )
        config.output_run_storage.write_run_metadata(
            output_run_dir,
            {
                "dataset_id": config.input_storage.dataset_id,
                "source_preprocessed_run": relative_run_path(root, source_run_dir),
                "feature_counts": counts,
                "features": list(config.feature_registry.keys()),
            },
        )

        opik_telemetry.flush()

    print(f"generate_features: wrote {len(written)} feature files to {output_run_dir}")
    return written
