from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest
from pydantic import BaseModel

from data_platform.generate_features.models import (
    FeatureGenerationConfig,
    FeatureRunConfig,
    FeatureSpec,
)
from data_platform.utils.feature_labels import FeatureLabelQuery
from data_platform.utils.storage import BlueskyStorageManager, StorageManager
from tests.data_platform.constants import (
    FEATURES_DATASET_ID,
    PREPROCESSED_RUN,
    PREPROCESSED_RUN_DIR,
    URI_POST_A,
    URI_POST_B,
)


class DummyModel:
    @staticmethod
    def model_fields() -> dict:
        return {"uri": None, "label_timestamp": None, "x": None}

    @staticmethod
    def model_validate(row: dict) -> DummyModel:
        return DummyModel()


@pytest.fixture
def features_dir(data_root: Path) -> Path:
    path = data_root / "bluesky" / FEATURES_DATASET_ID / "features"
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_feature_generation_config(
    features_dir: Path,
    *,
    dataset_id: str = FEATURES_DATASET_ID,
    feature_registry: dict[str, FeatureSpec] | None = None,
    run_config: FeatureRunConfig | None = None,
    preprocessed_run: str = PREPROCESSED_RUN,
) -> FeatureGenerationConfig:
    return FeatureGenerationConfig(
        platform="bluesky",
        id_column="uri",
        text_column="text",
        feature_registry=feature_registry or {},
        input_storage=BlueskyStorageManager("preprocessed", dataset_id),
        features_dir=features_dir,
        feature_label_query=FeatureLabelQuery(
            feature_storage=StorageManager(
                "bluesky", "features", BaseModel, dataset_id, records_filename="features"
            )
        ),
        run_config=run_config or FeatureRunConfig(opik_enabled=False),
        preprocessed_run=preprocessed_run,
    )


def write_preprocessed_posts(
    data_root: Path,
    records: list[Mapping[str, Any]],
    *,
    dataset_id: str = FEATURES_DATASET_ID,
    run_dir_name: str = PREPROCESSED_RUN_DIR,
) -> Path:
    preprocessed_dir = data_root / "bluesky" / dataset_id / "preprocessed" / run_dir_name
    preprocessed_dir.mkdir(parents=True)
    pd.DataFrame(list(records)).to_csv(preprocessed_dir / "posts.csv", index=False)
    return preprocessed_dir


@pytest.fixture
def mock_build_engine(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock_engine = MagicMock()
    monkeypatch.setattr(
        "data_platform.generate_features.generate_features.build_engine",
        lambda spec, run_config: mock_engine,
    )
    return mock_engine


def sample_preprocessed_records(
    count: int = 1,
) -> list[dict[str, str]]:
    uris = [URI_POST_A, URI_POST_B]
    texts = ["one", "two"]
    return [{"uri": uris[i], "text": texts[i]} for i in range(min(count, len(uris)))]
