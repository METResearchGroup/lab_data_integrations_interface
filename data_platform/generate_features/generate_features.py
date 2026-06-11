"""Resumable feature-generation orchestrator with batch execution engines."""

from __future__ import annotations

from collections.abc import Callable
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
    BatchRunStats,
    FeatureGenerationConfig,
    FeatureRunMetadata,
    FeatureSpec,
    LabelTask,
)
from data_platform.utils.storage import StorageManager
from ml_tooling.llm import opik as opik_telemetry


def tasks_from_dataframe(
    records: pd.DataFrame,
    id_column: str,
    text_column: str,
) -> list[LabelTask]:
    """Convert a posts dataframe into LabelTask rows for batch labeling."""
    if records.empty:
        return []
    return [
        LabelTask(uri=str(row[id_column]), text=str(row[text_column]))
        for _, row in records.iterrows()
    ]


def filter_records_needing_features(
    records: pd.DataFrame,
    feature_name: str,
    config: FeatureGenerationConfig,
) -> pd.DataFrame:
    """Return records that still need labels for feature_name."""
    return config.feature_label_query.filter_unlabeled(records, feature_name)


def _make_on_batch_complete(
    metadata: FeatureRunMetadata,
    feature_name: str,
    features_dir: Path,
) -> Callable[[int, int], None]:
    """Build a callback that flushes metadata after each atomic batch."""

    def on_batch_complete(labeled_delta: int, failed_delta: int) -> None:
        update_batch_counts(metadata, feature_name, labeled_delta, failed_delta)
        flush_metadata(features_dir, metadata)

    return on_batch_complete


def _run_feature_labeling(
    feature_name: str,
    spec: FeatureSpec,
    tasks: list[LabelTask],
    config: FeatureGenerationConfig,
    metadata: FeatureRunMetadata,
    feature_storage: StorageManager,
) -> BatchRunStats:
    """Execute batch labeling for one feature and update metadata on completion."""
    mark_feature_in_progress(metadata, feature_name)
    flush_metadata(config.features_dir, metadata)

    # LangChain or custom engine, each of which has their own way of managing
    # concurrency
    engine = build_engine(spec, config.run_config)
    stats = engine.label_records(
        tasks,
        feature_name=feature_name,
        feature_storage=feature_storage,
        batch_size=config.run_config.batch_size,
        on_batch_complete=_make_on_batch_complete(metadata, feature_name, config.features_dir),
    )

    total_labeled = metadata.features[feature_name].labeled
    mark_feature_completed(metadata, feature_name, total_labeled)
    flush_metadata(config.features_dir, metadata)
    return stats


def _process_one_feature(
    feature_name: str,
    spec: FeatureSpec,
    records: pd.DataFrame,
    config: FeatureGenerationConfig,
    metadata: FeatureRunMetadata,
) -> Path:
    """Label posts for a single feature and export labels."""
    feature_status = metadata.features.get(feature_name)
    feature_storage = StorageManager(
        config.platform,
        "features",
        spec.model,
        config.input_storage.dataset_id,
        records_filename=feature_name,
    )
    feature_path = feature_storage.root_dir / feature_storage.records_filename

    # Compare input posts against saved labels, to see which records need features.
    pending_df = filter_records_needing_features(records, feature_name, config)
    tasks = tasks_from_dataframe(pending_df, config.id_column, config.text_column)

    if len(tasks) == 0:
        # Every input post is already labeled — nothing to do.
        prior_labeled = feature_status.labeled if feature_status else 0
        mark_feature_completed(metadata, feature_name, prior_labeled)
        flush_metadata(config.features_dir, metadata)
        if feature_status and feature_status.status == "completed":
            # Idempotent rerun: feature was done before and still has no new posts.
            print(f"generate_features: skipping completed feature {feature_name}")
        else:
            # First run (or in-progress run) found no pending posts in this batch.
            print(f"generate_features: {feature_name} — nothing to label")
        return feature_path

    # Resume with new posts: a past batch of posts may have been done and
    # we marked the metadata as done, but we have new posts.
    if feature_status and feature_status.status == "completed":
        print(f"generate_features: {feature_name} was completed; labeling {len(tasks)} new posts")

    # Pending posts remain — run batch labeling and append to the feature file.
    stats = _run_feature_labeling(feature_name, spec, tasks, config, metadata, feature_storage)
    print(
        f"generate_features: {feature_name} -> {stats.labeled} new labels "
        f"({stats.failed_batches} failed batches) -> {feature_path}"
    )
    return feature_path


def _mark_sync_completed(
    metadata: FeatureRunMetadata,
    feature_names: tuple[str, ...],
    features_dir: Path,
) -> None:
    """Set sync_status completed when every feature entry is marked completed."""
    all_done = all(
        metadata.features.get(name) and metadata.features[name].status == "completed"
        for name in feature_names
    )
    if all_done:
        set_sync_status_completed(metadata)
        flush_metadata(features_dir, metadata)


def generate_features(
    records: pd.DataFrame,
    config: FeatureGenerationConfig,
) -> dict[str, Path]:
    """Generate configured features with resumable append to per-feature CSV files."""
    if records.empty:
        print("generate_features: no records to label")
        return {}

    feature_names = tuple(config.feature_registry.keys())
    metadata = load_or_init_metadata(
        config,
        feature_names=feature_names,
    )

    opik_telemetry.set_opik_enabled(config.run_config.opik_enabled)
    written: dict[str, Path] = {}

    with opik_telemetry.project_scope():
        for feature_name, spec in config.feature_registry.items():
            print(f"Generating features for {feature_name}")
            written[feature_name] = _process_one_feature(
                feature_name,
                spec,
                records,
                config,
                metadata,
            )
            print(f"Completed feature generation for {feature_name}")

        _mark_sync_completed(metadata, feature_names, config.features_dir)

        if config.run_config.opik_enabled:
            opik_telemetry.flush()

    print(f"generate_features: finished {len(written)} features under {config.features_dir}")
    return written
