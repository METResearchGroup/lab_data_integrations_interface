from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock

import pandas as pd
import pytest

from data_platform.generate_features.generate_bluesky_features import generate_bluesky_features
from data_platform.generate_features.models import FeatureRunMetadata
from tests.data_platform.constants import VALID_DATASET_ID


def _write_preprocessed_run(
    data_root: Path,
    dataset_id: str,
    run_name: str,
    *,
    s3_upload_status: bool,
) -> Path:
    run_dir = data_root / "bluesky" / dataset_id / "preprocessed" / run_name
    run_dir.mkdir(parents=True)
    (run_dir / "posts.csv").write_text("uri,text\nat://a/post/1,hello\n", encoding="utf-8")
    (run_dir / "metadata.json").write_text(
        json.dumps({"s3_upload_status": s3_upload_status}), encoding="utf-8"
    )
    return run_dir


def _write_features_meta(
    data_root: Path,
    dataset_id: str,
    *,
    s3_upload_status: bool,
    sync_status: Literal["pending", "in_progress", "completed"] = "completed",
) -> Path:
    features_dir = data_root / "bluesky" / dataset_id / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    meta = FeatureRunMetadata(
        dataset_id=dataset_id,
        source_preprocessed_runs=[],
        sync_status=sync_status,
        s3_upload_status=s3_upload_status,
    )
    (features_dir / "metadata.json").write_text(json.dumps(meta.to_dict()), encoding="utf-8")
    return features_dir


class TestFeatureGenGates:
    def test_gate_fails_if_no_preprocessed_runs(self, data_root: Path) -> None:
        with pytest.raises(FileNotFoundError):
            generate_bluesky_features(VALID_DATASET_ID)

    def test_gate_fails_if_preprocessed_not_uploaded(
        self, data_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_preprocessed_run(
            data_root, VALID_DATASET_ID, "2026_01_01-00:00:00", s3_upload_status=False
        )
        monkeypatch.setattr(
            "data_platform.generate_features.generate_bluesky_features._publish_feature",
            lambda *_: None,
        )
        with pytest.raises(RuntimeError):
            generate_bluesky_features(VALID_DATASET_ID)


class TestFeatureRetry:
    def test_retry_uploads_if_sync_complete_but_not_uploaded(
        self, data_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_preprocessed_run(
            data_root, VALID_DATASET_ID, "2026_01_01-00:00:00", s3_upload_status=True
        )
        features_dir = _write_features_meta(
            data_root, VALID_DATASET_ID, s3_upload_status=False, sync_status="completed"
        )
        feature_csv = features_dir / "is_political.csv"
        pd.DataFrame([{"uri": "at://a/post/1", "is_political": True}]).to_csv(
            feature_csv, index=False
        )

        mock_publish = MagicMock()
        monkeypatch.setattr(
            "data_platform.generate_features.generate_bluesky_features._publish_feature",
            mock_publish,
        )
        monkeypatch.setattr(
            "data_platform.generate_features.generate_bluesky_features.load_all_posts",
            lambda *_: pd.DataFrame(),
        )
        monkeypatch.setattr(
            "data_platform.generate_features.generate_bluesky_features.run_feature_generation",
            lambda *_, **__: {},
        )

        generate_bluesky_features(VALID_DATASET_ID)

        mock_publish.assert_called_once_with(VALID_DATASET_ID, "is_political", feature_csv)
