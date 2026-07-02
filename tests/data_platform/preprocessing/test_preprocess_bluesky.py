from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from data_platform.preprocessing.preprocess_bluesky import preprocess_records
from tests.data_platform.constants import VALID_DATASET_ID


def _write_raw_run(
    data_root: Path,
    dataset_id: str,
    run_name: str,
    *,
    s3_upload_status: bool,
) -> Path:
    run_dir = data_root / "bluesky" / dataset_id / "raw" / run_name
    run_dir.mkdir(parents=True)
    (run_dir / "metadata.json").write_text(
        json.dumps({"s3_upload_status": s3_upload_status}), encoding="utf-8"
    )
    return run_dir


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


class TestPreprocessGates:
    def test_gate_fails_if_no_raw_runs(self, data_root: Path) -> None:
        with pytest.raises(FileNotFoundError):
            preprocess_records(VALID_DATASET_ID)

    def test_gate_fails_if_raw_not_uploaded(self, data_root: Path) -> None:
        _write_raw_run(data_root, VALID_DATASET_ID, "2026_01_01-00:00:00", s3_upload_status=False)
        with pytest.raises(RuntimeError):
            preprocess_records(VALID_DATASET_ID)


class TestPreprocessRetry:
    def test_retry_uploads_pending_run(
        self, data_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stale_run_dir = _write_preprocessed_run(
            data_root, VALID_DATASET_ID, "2026_01_01-00:00:00", s3_upload_status=False
        )

        # Created only once run_preprocess_records is invoked, i.e. *after* the retry
        # sweep already ran -- mirrors how a real new run wouldn't exist on disk yet
        # when preprocess_records starts.
        def fake_run_preprocess_records(*_args: object) -> Path:
            return _write_preprocessed_run(
                data_root, VALID_DATASET_ID, "2026_01_01-00:05:00", s3_upload_status=False
            )

        mock_publish = MagicMock()
        monkeypatch.setattr(
            "data_platform.preprocessing.preprocess_bluesky._publish_preprocessed_run",
            mock_publish,
        )
        monkeypatch.setattr(
            "data_platform.preprocessing.preprocess_bluesky.run_preprocess_records",
            fake_run_preprocess_records,
        )

        preprocess_records(VALID_DATASET_ID)

        # The stale run gets published via the retry sweep; the current run gets
        # published as part of the main preprocess_records flow (which now always
        # runs, even for an empty result -- see preprocess_records's Path-only contract).
        current_run_dir = (
            data_root / "bluesky" / VALID_DATASET_ID / "preprocessed" / "2026_01_01-00:05:00"
        )
        assert mock_publish.call_args_list == [
            call(VALID_DATASET_ID, stale_run_dir, stale_run_dir / "posts.csv"),
            call(VALID_DATASET_ID, current_run_dir, current_run_dir / "posts.csv"),
        ]
        for run_dir in (stale_run_dir, current_run_dir):
            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
            assert metadata["s3_upload_status"] is True
