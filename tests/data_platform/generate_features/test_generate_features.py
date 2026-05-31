from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from data_platform.generate_features.generate_features import generate_features
from data_platform.generate_features.metadata import flush_metadata, load_or_init_metadata
from data_platform.generate_features.models import (
    BatchRunStats,
    FeatureGenerationConfig,
    FeatureRunConfig,
    FeatureSpec,
    FeatureStatus,
)
from data_platform.utils.feature_labels import FeatureLabelQuery
from data_platform.utils.storage import BlueskyStorageManager


class _DummyModel:
    @staticmethod
    def model_fields() -> dict:
        return {"uri": None, "label_timestamp": None, "x": None}

    @staticmethod
    def model_validate(row: dict) -> "_DummyModel":
        return _DummyModel()


def _patch_data_roots(tmp_path: Path) -> None:
    import data_platform.utils.dataset as dataset_mod
    import data_platform.utils.storage as storage_mod

    data_root = tmp_path / "data"
    storage_mod.DATA_ROOT = data_root
    dataset_mod._DATA_ROOT = data_root


def test_skips_completed_features(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_data_roots(tmp_path)
    dataset_id = "bluesky_f47ac10b-58cc-4372-a567-0e02b2c3d479"
    features_dir = tmp_path / "features"
    features_dir.mkdir(parents=True)
    preprocessed_dir = tmp_path / "data" / "bluesky" / dataset_id / "preprocessed" / "2026_01_01-00:00:00"
    preprocessed_dir.mkdir(parents=True)
    pd.DataFrame([{"uri": "at://a/post/1", "text": "one"}]).to_csv(
        preprocessed_dir / "posts.csv",
        index=False,
    )

    spec = FeatureSpec(
        name="feat_a",
        model=_DummyModel,  # type: ignore[arg-type]
        engine_type="thread_pool",
        generate_fn=lambda u, t: None,  # type: ignore[arg-type]
    )
    metadata = load_or_init_metadata(
        features_dir,
        dataset_id,
        "preprocessed/2026_01_01-00:00:00",
        FeatureRunConfig(opik_enabled=False),
        feature_names=("feat_a",),
    )
    metadata.features["feat_a"] = FeatureStatus(status="completed", labeled=1)
    flush_metadata(features_dir, metadata)

    mock_engine = MagicMock()
    monkeypatch.setattr(
        "data_platform.generate_features.generate_features.build_engine",
        lambda spec, run_config: mock_engine,
    )

    records = pd.DataFrame([{"uri": "at://a/post/1", "text": "one"}])
    config = FeatureGenerationConfig(
        platform="bluesky",
        id_column="uri",
        text_column="text",
        feature_registry={"feat_a": spec},
        input_storage=BlueskyStorageManager("preprocessed", dataset_id),
        features_dir=features_dir,
        feature_label_query=FeatureLabelQuery(features_root=features_dir),
        run_config=FeatureRunConfig(opik_enabled=False),
    )
    generate_features(records, config)
    mock_engine.label_records.assert_not_called()


def test_orchestrator_calls_label_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_data_roots(tmp_path)
    dataset_id = "bluesky_f47ac10b-58cc-4372-a567-0e02b2c3d479"
    features_dir = tmp_path / "features"
    features_dir.mkdir(parents=True)
    preprocessed_dir = tmp_path / "data" / "bluesky" / dataset_id / "preprocessed" / "2026_01_01-00:00:00"
    preprocessed_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"uri": "at://a/post/1", "text": "one"},
            {"uri": "at://b/post/2", "text": "two"},
        ]
    ).to_csv(preprocessed_dir / "posts.csv", index=False)

    spec = FeatureSpec(
        name="feat_a",
        model=_DummyModel,  # type: ignore[arg-type]
        engine_type="thread_pool",
        generate_fn=lambda u, t: None,  # type: ignore[arg-type]
    )
    mock_engine = MagicMock()
    mock_engine.label_records.return_value = BatchRunStats(labeled=2, failed_batches=0)
    monkeypatch.setattr(
        "data_platform.generate_features.generate_features.build_engine",
        lambda spec, run_config: mock_engine,
    )

    records = pd.DataFrame(
        [
            {"uri": "at://a/post/1", "text": "one"},
            {"uri": "at://b/post/2", "text": "two"},
        ]
    )
    config = FeatureGenerationConfig(
        platform="bluesky",
        id_column="uri",
        text_column="text",
        feature_registry={"feat_a": spec},
        input_storage=BlueskyStorageManager("preprocessed", dataset_id),
        features_dir=features_dir,
        feature_label_query=FeatureLabelQuery(features_root=features_dir),
        run_config=FeatureRunConfig(opik_enabled=False, batch_size=2),
    )
    generate_features(records, config)
    mock_engine.label_records.assert_called_once()
