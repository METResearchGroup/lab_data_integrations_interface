"""Load and flush features/metadata.json for resumable feature generation."""

from __future__ import annotations

import json
from pathlib import Path

from data_platform.generate_features.models import (
    FeatureGenerationConfig,
    FeatureRunMetadata,
    FeatureStatus,
)
from data_platform.utils.dataset import dataset_root, relative_run_path
from data_platform.utils.storage import METADATA_FILENAME
from lib.timestamp_utils import get_current_timestamp


def metadata_path(features_dir: Path) -> Path:
    """Return the path to features/metadata.json for a dataset."""
    return features_dir / METADATA_FILENAME


def flush_metadata(features_dir: Path, metadata: FeatureRunMetadata) -> None:
    """Atomically write metadata.json under features_dir with an updated timestamp."""
    features_dir.mkdir(parents=True, exist_ok=True)
    metadata.updated_at = get_current_timestamp()
    path = metadata_path(features_dir)
    tmp_path = features_dir / f"{METADATA_FILENAME}.tmp"
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(metadata.to_dict(), f, indent=2)
    tmp_path.replace(path)


def resolve_source_preprocessed_run(
    config: FeatureGenerationConfig,
    preprocessed_run: str | None,
) -> str:
    """Return a pinned or latest preprocessed run path relative to the dataset root."""
    if preprocessed_run:
        return preprocessed_run
    source_run_dir = config.input_storage.latest_run_dir()
    if source_run_dir is None:
        raise FileNotFoundError(f"No preprocessed runs found under {config.input_storage.root_dir}")
    root = dataset_root(config.platform, config.input_storage.dataset_id)
    return relative_run_path(root, source_run_dir)


def load_or_init_metadata(
    config: FeatureGenerationConfig,
    *,
    feature_names: tuple[str, ...],
) -> FeatureRunMetadata:
    """Load existing feature-run metadata or create a new in-progress document."""
    path = metadata_path(config.features_dir)
    if path.exists():
        with path.open(encoding="utf-8") as f:
            return FeatureRunMetadata.from_dict(json.load(f))

    source_preprocessed_run = resolve_source_preprocessed_run(
        config,
        config.preprocessed_run,
    )
    features = {name: FeatureStatus() for name in feature_names}
    metadata = FeatureRunMetadata(
        dataset_id=config.input_storage.dataset_id,
        source_preprocessed_run=source_preprocessed_run,
        sync_status="in_progress",
        features=features,
        config=config.run_config,
        updated_at=get_current_timestamp(),
    )
    flush_metadata(config.features_dir, metadata)
    return metadata


def mark_feature_in_progress(
    metadata: FeatureRunMetadata,
    feature_name: str,
) -> FeatureRunMetadata:
    """Mark one feature as in_progress and set the overall sync status accordingly."""
    status = metadata.features.setdefault(feature_name, FeatureStatus())
    status.status = "in_progress"
    metadata.sync_status = "in_progress"
    return metadata


def mark_feature_completed(
    metadata: FeatureRunMetadata,
    feature_name: str,
    labeled: int,
) -> FeatureRunMetadata:
    """Mark one feature completed and record its final labeled row count."""
    status = metadata.features.setdefault(feature_name, FeatureStatus())
    status.status = "completed"
    status.labeled = labeled
    return metadata


def update_batch_counts(
    metadata: FeatureRunMetadata,
    feature_name: str,
    labeled_delta: int,
    failed_batches_delta: int,
) -> FeatureRunMetadata:
    """Increment labeled and failed-batch counters after an atomic batch finishes."""
    status = metadata.features.setdefault(feature_name, FeatureStatus())
    status.labeled += labeled_delta
    status.failed_batches += failed_batches_delta
    return metadata


def set_sync_status_completed(metadata: FeatureRunMetadata) -> FeatureRunMetadata:
    """Set sync_status to completed when every feature in the registry has finished."""
    metadata.sync_status = "completed"
    return metadata
