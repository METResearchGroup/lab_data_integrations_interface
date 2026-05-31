"""Resumable feature-generation orchestrator with batch execution engines."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_platform.generate_features.engines import build_engine
from data_platform.generate_features.metadata import (
    flush_metadata,
    load_or_init_metadata,
    mark_feature_completed,
    mark_feature_in_progress,
    set_sync_status_completed,
    update_batch_counts,
)
from data_platform.generate_features.models import (
    FeatureGenerationConfig,
    LabelTask,
)
from data_platform.utils.dataset import dataset_root, relative_run_path
from data_platform.utils.duckdb_features import flat_feature_csv
from ml_tooling.llm import opik as opik_telemetry


def tasks_from_dataframe(
    records: pd.DataFrame,
    id_column: str,
    text_column: str,
) -> list[LabelTask]:
    if records.empty:
        return []
    return [
        LabelTask(uri=str(row[id_column]), text=str(row[text_column]))
        for _, row in records.iterrows()
    ]


def resolve_source_preprocessed_run(
    config: FeatureGenerationConfig,
    preprocessed_run: str | None,
) -> str:
    if preprocessed_run:
        return preprocessed_run
    source_run_dir = config.input_storage.latest_run_dir()
    if source_run_dir is None:
        raise FileNotFoundError(f"No preprocessed runs found under {config.input_storage.root_dir}")
    root = dataset_root(config.platform, config.input_storage.dataset_id)
    return relative_run_path(root, source_run_dir)


def filter_records_needing_features(
    records: pd.DataFrame,
    feature_name: str,
    config: FeatureGenerationConfig,
) -> pd.DataFrame:
    """Return records that still need labels for feature_name."""
    return config.feature_label_query.filter_unlabeled(records, feature_name)


def generate_features(
    records: pd.DataFrame,
    config: FeatureGenerationConfig,
) -> dict[str, Path]:
    """Generate all configured features with resumable flat CSV append."""
    if records.empty:
        print("generate_features: no records to label")
        return {}

    source_preprocessed_run = resolve_source_preprocessed_run(
        config,
        config.preprocessed_run,
    )
    feature_names = tuple(config.feature_registry.keys())
    metadata = load_or_init_metadata(
        config.features_dir,
        config.input_storage.dataset_id,
        source_preprocessed_run,
        config.run_config,
        feature_names=feature_names,
    )

    opik_telemetry.set_opik_enabled(config.run_config.opik_enabled)
    written: dict[str, Path] = {}

    with opik_telemetry.project_scope():
        for feature_name, spec in config.feature_registry.items():
            feature_status = metadata.features.get(feature_name)
            if feature_status and feature_status.status == "completed":
                print(f"generate_features: skipping completed feature {feature_name}")
                written[feature_name] = flat_feature_csv(config.features_dir, feature_name)
                continue

            pending_df = filter_records_needing_features(records, feature_name, config)
            tasks = tasks_from_dataframe(
                pending_df,
                config.id_column,
                config.text_column,
            )
            if not tasks:
                prior_labeled = feature_status.labeled if feature_status else 0
                mark_feature_completed(metadata, feature_name, prior_labeled)
                flush_metadata(config.features_dir, metadata)
                written[feature_name] = flat_feature_csv(config.features_dir, feature_name)
                print(f"generate_features: {feature_name} — nothing to label")
                continue

            mark_feature_in_progress(metadata, feature_name)
            flush_metadata(config.features_dir, metadata)

            engine = build_engine(spec, config.run_config)

            def on_batch_complete(labeled_delta: int, failed_delta: int) -> None:
                update_batch_counts(metadata, feature_name, labeled_delta, failed_delta)
                flush_metadata(config.features_dir, metadata)

            stats = engine.label_records(
                tasks,
                feature_name=feature_name,
                features_dir=config.features_dir,
                batch_size=config.run_config.batch_size,
                on_batch_complete=on_batch_complete,
            )

            total_labeled = metadata.features[feature_name].labeled
            mark_feature_completed(metadata, feature_name, total_labeled)
            flush_metadata(config.features_dir, metadata)
            csv_path = flat_feature_csv(config.features_dir, feature_name)
            written[feature_name] = csv_path
            print(
                f"generate_features: {feature_name} -> {stats.labeled} new labels "
                f"({stats.failed_batches} failed batches) -> {csv_path}"
            )

        all_done = all(
            metadata.features.get(name) and metadata.features[name].status == "completed"
            for name in feature_names
        )
        if all_done:
            set_sync_status_completed(metadata)
            flush_metadata(config.features_dir, metadata)

        if config.run_config.opik_enabled:
            opik_telemetry.flush()

    print(f"generate_features: finished {len(written)} features under {config.features_dir}")
    return written
