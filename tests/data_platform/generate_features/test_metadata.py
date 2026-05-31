from __future__ import annotations

import json
from pathlib import Path

from data_platform.generate_features.metadata import (
    flush_metadata,
    load_or_init_metadata,
    mark_feature_completed,
    mark_feature_in_progress,
    metadata_path,
    set_sync_status_completed,
    update_batch_counts,
)
from data_platform.generate_features.models import (
    FeatureRunConfig,
    FeatureRunMetadata,
    FeatureStatus,
)


def test_load_or_init_metadata_creates_file(tmp_path: Path) -> None:
    features_dir = tmp_path / "features"
    config = FeatureRunConfig(batch_size=32, opik_enabled=False)
    metadata = load_or_init_metadata(
        features_dir,
        "bluesky_f47ac10b-58cc-4372-a567-0e02b2c3d479",
        "preprocessed/2026_01_01-00:00:00",
        config,
        feature_names=("is_political",),
    )
    assert metadata_path(features_dir).exists()
    assert metadata.features["is_political"].status == "pending"
    assert metadata.config.batch_size == 32


def test_flush_metadata_round_trip(tmp_path: Path) -> None:
    features_dir = tmp_path / "features"
    metadata = FeatureRunMetadata(
        dataset_id="bluesky_f47ac10b-58cc-4372-a567-0e02b2c3d479",
        source_preprocessed_run="preprocessed/2026_01_01-00:00:00",
        config=FeatureRunConfig(),
    )
    metadata.features["is_political"] = FeatureStatus()
    mark_feature_in_progress(metadata, "is_political")
    update_batch_counts(metadata, "is_political", labeled_delta=5, failed_batches_delta=1)
    mark_feature_completed(metadata, "is_political", labeled=5)
    set_sync_status_completed(metadata)
    flush_metadata(features_dir, metadata)

    with metadata_path(features_dir).open(encoding="utf-8") as f:
        data = json.load(f)
    assert data["sync_status"] == "completed"
    assert data["features"]["is_political"]["labeled"] == 5
    assert data["features"]["is_political"]["failed_batches"] == 1
