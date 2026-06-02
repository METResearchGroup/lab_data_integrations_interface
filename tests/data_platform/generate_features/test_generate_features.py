from __future__ import annotations

import pandas as pd

from data_platform.generate_features.generate_bluesky_features import (
    generate_bluesky_features,
)
from data_platform.generate_features.generate_features import generate_features
from data_platform.generate_features.metadata import flush_metadata, load_or_init_metadata
from data_platform.generate_features.models import (
    BatchRunStats,
    FeatureRunConfig,
    FeatureSpec,
    FeatureStatus,
)
from tests.data_platform.constants import (
    FEATURES_DATASET_ID,
    LABEL_TIMESTAMP,
    URI_POST_A,
    URI_POST_B,
)
from tests.data_platform.generate_features.conftest import (
    DummyModel,
    make_feature_generation_config,
    sample_preprocessed_records,
    write_preprocessed_posts,
)


def test_skips_completed_features(
    data_root,
    features_dir,
    mock_build_engine,
) -> None:
    write_preprocessed_posts(data_root, sample_preprocessed_records(1))

    spec = FeatureSpec(
        name="feat_a",
        model=DummyModel,  # type: ignore[arg-type]
        engine_type="thread_pool",
        generate_fn=lambda u, t: None,  # type: ignore[arg-type]
    )
    config = make_feature_generation_config(
        features_dir,
        feature_registry={"feat_a": spec},
    )
    metadata = load_or_init_metadata(config, feature_names=("feat_a",))
    metadata.features["feat_a"] = FeatureStatus(status="completed", labeled=1)
    flush_metadata(features_dir, metadata)
    pd.DataFrame(
        [{"uri": URI_POST_A, "label_timestamp": LABEL_TIMESTAMP, "x": 1}],
    ).to_csv(features_dir / "feat_a.csv", index=False)

    records = pd.DataFrame([{"uri": URI_POST_A, "text": "one"}])
    generate_features(records, config)
    mock_build_engine.label_records.assert_not_called()


def test_reopens_completed_feature_with_new_posts(
    data_root,
    features_dir,
    mock_build_engine,
) -> None:
    write_preprocessed_posts(data_root, sample_preprocessed_records(2))

    spec = FeatureSpec(
        name="feat_a",
        model=DummyModel,  # type: ignore[arg-type]
        engine_type="thread_pool",
        generate_fn=lambda u, t: None,  # type: ignore[arg-type]
    )
    config = make_feature_generation_config(
        features_dir,
        feature_registry={"feat_a": spec},
    )
    metadata = load_or_init_metadata(config, feature_names=("feat_a",))
    metadata.features["feat_a"] = FeatureStatus(status="completed", labeled=1)
    flush_metadata(features_dir, metadata)
    pd.DataFrame(
        [{"uri": URI_POST_A, "label_timestamp": LABEL_TIMESTAMP, "x": 1}],
    ).to_csv(features_dir / "feat_a.csv", index=False)

    mock_build_engine.label_records.return_value = BatchRunStats(labeled=1, failed_batches=0)

    records = pd.DataFrame(
        [
            {"uri": URI_POST_A, "text": "one"},
            {"uri": URI_POST_B, "text": "two"},
        ]
    )
    generate_features(records, config)
    mock_build_engine.label_records.assert_called_once()


def test_orchestrator_calls_label_records(
    data_root,
    features_dir,
    mock_build_engine,
) -> None:
    write_preprocessed_posts(data_root, sample_preprocessed_records(2))

    spec = FeatureSpec(
        name="feat_a",
        model=DummyModel,  # type: ignore[arg-type]
        engine_type="thread_pool",
        generate_fn=lambda u, t: None,  # type: ignore[arg-type]
    )
    mock_build_engine.label_records.return_value = BatchRunStats(labeled=2, failed_batches=0)

    records = pd.DataFrame(
        [
            {"uri": URI_POST_A, "text": "one"},
            {"uri": URI_POST_B, "text": "two"},
        ]
    )
    config = make_feature_generation_config(
        features_dir,
        feature_registry={"feat_a": spec},
        run_config=FeatureRunConfig(opik_enabled=False, batch_size=2),
    )
    generate_features(records, config)
    mock_build_engine.label_records.assert_called_once()


def test_default_feature_run_config_disables_opik() -> None:
    assert FeatureRunConfig().opik_enabled is False


def test_generate_bluesky_features_defaults_to_opik_disabled(
    monkeypatch,
    data_root,
) -> None:
    captured = {}

    def fake_run_feature_generation(records, config, *, empty_message):
        captured["opik_enabled"] = config.run_config.opik_enabled
        return {}

    monkeypatch.setattr(
        "data_platform.generate_features.generate_bluesky_features.run_feature_generation",
        fake_run_feature_generation,
    )
    monkeypatch.setattr(
        "data_platform.generate_features.generate_bluesky_features.load_posts",
        lambda dataset_id, preprocessed_run=None: pd.DataFrame([{"uri": "1", "text": "hello"}]),
    )

    generate_bluesky_features(FEATURES_DATASET_ID)
    assert captured["opik_enabled"] is False
