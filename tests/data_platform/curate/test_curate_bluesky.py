from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from data_platform.curate.curate_bluesky import curate
from data_platform.generate_features.models import FeatureRunMetadata
from tests.data_platform.constants import VALID_DATASET_ID

MINIMAL_CONFIG = "name: test\noutput:\n  stem: test\nfilters: []\n"


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
) -> None:
    features_dir = data_root / "bluesky" / dataset_id / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    meta = FeatureRunMetadata(
        dataset_id=dataset_id,
        source_preprocessed_runs=[],
        sync_status="completed",
        s3_upload_status=s3_upload_status,
    )
    (features_dir / "metadata.json").write_text(json.dumps(meta.to_dict()), encoding="utf-8")


def _write_curated_run(
    data_root: Path,
    dataset_id: str,
    run_name: str,
    *,
    s3_upload_status: bool,
    source_preprocessed_runs: list[str],
    rules_hash: str,
    export_filename: str = "test.csv",
    write_output_file: bool = True,
) -> Path:
    run_dir = data_root / "bluesky" / dataset_id / "curated" / run_name
    run_dir.mkdir(parents=True)
    if write_output_file:
        (run_dir / export_filename).write_text("uri\n", encoding="utf-8")
    (run_dir / "metadata.json").write_text(
        json.dumps(
            {
                "s3_upload_status": s3_upload_status,
                "source_preprocessed_runs": source_preprocessed_runs,
                "rules_hash": rules_hash,
                "files": {"export": export_filename},
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def _make_fake_new_run(
    data_root: Path, dataset_id: str, run_name: str = "2026_06_26-00:00:00"
) -> Path:
    """Create a fake curated run dir that satisfies the post-run_curation code path."""
    new_run_dir = data_root / "bluesky" / dataset_id / "curated" / run_name
    new_run_dir.mkdir(parents=True)
    fake_output = new_run_dir / "test.csv"
    fake_output.write_text("")
    (new_run_dir / "metadata.json").write_text(
        json.dumps({"s3_upload_status": False}), encoding="utf-8"
    )
    return fake_output


def _config_and_hash(tmp_path: Path, content: str = MINIMAL_CONFIG) -> tuple[Path, str]:
    config_path = tmp_path / "test.yaml"
    config_path.write_text(content)
    rules_hash = hashlib.sha256(content.encode()).hexdigest()
    return config_path, rules_hash


class TestCurateGates:
    def test_gate_fails_if_features_metadata_missing(self, data_root: Path, tmp_path: Path) -> None:
        config_path, _ = _config_and_hash(tmp_path)
        with pytest.raises(FileNotFoundError):
            curate(config_path, VALID_DATASET_ID)

    def test_gate_fails_if_features_not_uploaded(self, data_root: Path, tmp_path: Path) -> None:
        _write_features_meta(data_root, VALID_DATASET_ID, s3_upload_status=False)
        config_path, _ = _config_and_hash(tmp_path)
        with pytest.raises(RuntimeError):
            curate(config_path, VALID_DATASET_ID)

    def test_gate_fails_if_preprocessed_not_uploaded(self, data_root: Path, tmp_path: Path) -> None:
        _write_features_meta(data_root, VALID_DATASET_ID, s3_upload_status=True)
        _write_preprocessed_run(
            data_root, VALID_DATASET_ID, "2026_01_01-00:00:00", s3_upload_status=False
        )
        config_path, _ = _config_and_hash(tmp_path)
        with pytest.raises(RuntimeError):
            curate(config_path, VALID_DATASET_ID)


class TestCurateEarlyExit:
    def test_skips_if_already_up_to_date(
        self, data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_path, rules_hash = _config_and_hash(tmp_path)
        _write_features_meta(data_root, VALID_DATASET_ID, s3_upload_status=True)
        _write_preprocessed_run(
            data_root, VALID_DATASET_ID, "2026_01_01-00:00:00", s3_upload_status=True
        )
        existing_run = _write_curated_run(
            data_root,
            VALID_DATASET_ID,
            "2026_06_01-00:00:00",
            s3_upload_status=True,
            source_preprocessed_runs=["preprocessed/2026_01_01-00:00:00"],
            rules_hash=rules_hash,
        )

        mock_run_curation = MagicMock()
        monkeypatch.setattr("data_platform.curate.curate_bluesky.run_curation", mock_run_curation)
        monkeypatch.setattr(
            "data_platform.curate.curate_bluesky._publish_curated_run", lambda *_: None
        )

        result = curate(config_path, VALID_DATASET_ID)

        mock_run_curation.assert_not_called()
        assert result == existing_run / "test.csv"

    def test_reruns_if_new_preprocessed_run(
        self, data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_path, rules_hash = _config_and_hash(tmp_path)
        _write_features_meta(data_root, VALID_DATASET_ID, s3_upload_status=True)
        _write_preprocessed_run(
            data_root, VALID_DATASET_ID, "2026_01_01-00:00:00", s3_upload_status=True
        )
        _write_curated_run(
            data_root,
            VALID_DATASET_ID,
            "2026_06_01-00:00:00",
            s3_upload_status=True,
            source_preprocessed_runs=["preprocessed/2026_01_01-00:00:00"],
            rules_hash=rules_hash,
        )
        # Second preprocessed run added after curated run was created
        _write_preprocessed_run(
            data_root, VALID_DATASET_ID, "2026_02_01-00:00:00", s3_upload_status=True
        )

        fake_output = _make_fake_new_run(data_root, VALID_DATASET_ID)
        mock_run_curation = MagicMock(return_value=fake_output)
        monkeypatch.setattr("data_platform.curate.curate_bluesky.run_curation", mock_run_curation)
        monkeypatch.setattr(
            "data_platform.curate.curate_bluesky._publish_curated_run", lambda *_: None
        )

        curate(config_path, VALID_DATASET_ID)

        mock_run_curation.assert_called_once()

    def test_reruns_if_rules_hash_changed(
        self, data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_path, _ = _config_and_hash(tmp_path)
        _write_features_meta(data_root, VALID_DATASET_ID, s3_upload_status=True)
        _write_preprocessed_run(
            data_root, VALID_DATASET_ID, "2026_01_01-00:00:00", s3_upload_status=True
        )
        _write_curated_run(
            data_root,
            VALID_DATASET_ID,
            "2026_06_01-00:00:00",
            s3_upload_status=True,
            source_preprocessed_runs=["preprocessed/2026_01_01-00:00:00"],
            rules_hash="stale_hash_from_old_config",
        )

        fake_output = _make_fake_new_run(data_root, VALID_DATASET_ID)
        mock_run_curation = MagicMock(return_value=fake_output)
        monkeypatch.setattr("data_platform.curate.curate_bluesky.run_curation", mock_run_curation)
        monkeypatch.setattr(
            "data_platform.curate.curate_bluesky._publish_curated_run", lambda *_: None
        )

        curate(config_path, VALID_DATASET_ID)

        mock_run_curation.assert_called_once()

    def test_reruns_if_last_curated_not_uploaded(
        self, data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_path, rules_hash = _config_and_hash(tmp_path)
        _write_features_meta(data_root, VALID_DATASET_ID, s3_upload_status=True)
        _write_preprocessed_run(
            data_root, VALID_DATASET_ID, "2026_01_01-00:00:00", s3_upload_status=True
        )
        # No output file -> retry can't fix this; _is_up_to_date sees s3_upload_status=False
        _write_curated_run(
            data_root,
            VALID_DATASET_ID,
            "2026_06_01-00:00:00",
            s3_upload_status=False,
            source_preprocessed_runs=["preprocessed/2026_01_01-00:00:00"],
            rules_hash=rules_hash,
            write_output_file=False,
        )

        fake_output = _make_fake_new_run(data_root, VALID_DATASET_ID)
        mock_run_curation = MagicMock(return_value=fake_output)
        monkeypatch.setattr("data_platform.curate.curate_bluesky.run_curation", mock_run_curation)
        monkeypatch.setattr(
            "data_platform.curate.curate_bluesky._publish_curated_run", lambda *_: None
        )

        curate(config_path, VALID_DATASET_ID)

        mock_run_curation.assert_called_once()


class TestCurateRetry:
    def test_retry_uploads_pending_run(
        self, data_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_path, rules_hash = _config_and_hash(tmp_path)
        _write_features_meta(data_root, VALID_DATASET_ID, s3_upload_status=True)
        _write_preprocessed_run(
            data_root, VALID_DATASET_ID, "2026_01_01-00:00:00", s3_upload_status=True
        )
        # Pending run has matching source+hash so that after retry fixes s3_upload_status,
        # _is_up_to_date returns the existing path (no new run needed)
        pending_run = _write_curated_run(
            data_root,
            VALID_DATASET_ID,
            "2026_06_01-00:00:00",
            s3_upload_status=False,
            source_preprocessed_runs=["preprocessed/2026_01_01-00:00:00"],
            rules_hash=rules_hash,
        )

        mock_publish = MagicMock()
        monkeypatch.setattr(
            "data_platform.curate.curate_bluesky._publish_curated_run", mock_publish
        )

        result = curate(config_path, VALID_DATASET_ID)

        mock_publish.assert_called_once()
        assert mock_publish.call_args[0][1] == pending_run
        assert result == pending_run / "test.csv"
