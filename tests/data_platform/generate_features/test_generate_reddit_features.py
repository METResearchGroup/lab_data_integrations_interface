from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from data_platform.generate_features.generate_features import generate_features
from data_platform.generate_features.generate_reddit_features import (
    FEATURE_CSV_ID_COLUMN,
    ID_COLUMN,
    TEXT_COLUMN,
    generate_reddit_features,
    load_comments,
    reddit_feature_config,
)
from data_platform.generate_features.metadata import flush_metadata, load_or_init_metadata
from data_platform.generate_features.models import (
    BatchRunStats,
    FeatureRunConfig,
    FeatureSpec,
    FeatureStatus,
)
from tests.data_platform.constants import LABEL_TIMESTAMP, VALID_REDDIT_DATASET_ID
from tests.data_platform.generate_features.conftest import DummyModel
from tests.data_platform.ingestion.reddit_conftest import mock_comment_row


def _sample_preprocessed_comments(count: int = 1) -> list[dict[str, Any]]:
    return [
        mock_comment_row(
            f"t1_comment_{index}",
            subreddit="politics",
        )
        for index in range(count)
    ]


def write_preprocessed_comments(
    data_root: Path,
    records: list[dict[str, Any]],
    *,
    dataset_id: str = VALID_REDDIT_DATASET_ID,
    run_dir_name: str = "2026_06_01-00:00:00",
) -> Path:
    preprocessed_dir = data_root / "reddit" / dataset_id / "preprocessed" / run_dir_name
    preprocessed_dir.mkdir(parents=True)
    pd.DataFrame(records).to_csv(preprocessed_dir / "comments.csv", index=False)
    return preprocessed_dir


def make_reddit_feature_generation_config(
    *,
    dataset_id: str = VALID_REDDIT_DATASET_ID,
    feature_registry: dict[str, FeatureSpec] | None = None,
    run_config: FeatureRunConfig | None = None,
    preprocessed_run: str = "preprocessed/2026_06_01-00:00:00",
):
    return reddit_feature_config(
        dataset_id,
        run_config=run_config or FeatureRunConfig(opik_enabled=False),
        preprocessed_run=preprocessed_run,
        features_subset=tuple(feature_registry.keys()) if feature_registry else None,
    )


def test_reddit_feature_config_bindings(data_root) -> None:
    config = reddit_feature_config(
        VALID_REDDIT_DATASET_ID,
        run_config=FeatureRunConfig(opik_enabled=False),
        preprocessed_run="preprocessed/2026_06_01-00:00:00",
    )
    assert config.platform == "reddit"
    assert config.id_column == ID_COLUMN
    assert config.text_column == TEXT_COLUMN
    assert config.feature_label_query.id_column == ID_COLUMN
    assert config.feature_label_query.feature_csv_id_column == FEATURE_CSV_ID_COLUMN
    assert config.input_storage.platform == "reddit"


def test_load_comments_reads_latest_preprocessed_run(data_root) -> None:
    records = _sample_preprocessed_comments(2)
    write_preprocessed_comments(data_root, records)

    comments = load_comments(VALID_REDDIT_DATASET_ID)
    assert len(comments) == 2
    assert ID_COLUMN in comments.columns
    assert TEXT_COLUMN in comments.columns


def test_generate_reddit_features_skips_completed_feature(
    data_root,
    mock_build_engine,
) -> None:
    records = _sample_preprocessed_comments(1)
    write_preprocessed_comments(data_root, records)

    spec = FeatureSpec(
        name="is_political",
        model=DummyModel,  # type: ignore[arg-type]
        engine_type="thread_pool",
        generate_fn=lambda _u, _t: None,  # type: ignore[arg-type]
    )
    config = make_reddit_feature_generation_config(feature_registry={"is_political": spec})
    metadata = load_or_init_metadata(config, feature_names=("is_political",))
    metadata.features["is_political"] = FeatureStatus(status="completed", labeled=1)
    flush_metadata(config.features_dir, metadata)
    pd.DataFrame(
        [
            {
                FEATURE_CSV_ID_COLUMN: records[0][ID_COLUMN],
                "label_timestamp": LABEL_TIMESTAMP,
                "is_political": True,
            }
        ],
    ).to_csv(config.features_dir / "is_political.csv", index=False)

    comments = pd.DataFrame(records)
    generate_features(comments, config)
    mock_build_engine.label_records.assert_not_called()


def test_generate_reddit_features_labels_pending_comments(
    data_root,
    mock_build_engine,
) -> None:
    records = _sample_preprocessed_comments(2)
    write_preprocessed_comments(data_root, records)

    mock_build_engine.label_records.return_value = BatchRunStats(labeled=2, failed_batches=0)

    written = generate_reddit_features(
        VALID_REDDIT_DATASET_ID,
        no_opik=True,
        feature_subset=["is_political"],
    )
    assert "is_political" in written
    mock_build_engine.label_records.assert_called_once()
