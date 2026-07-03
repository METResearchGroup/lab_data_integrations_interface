from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_platform.utils.storage import METADATA_FILENAME, BlueskyStorageManager, StorageStage
from tests.data_platform.constants import VALID_DATASET_ID


@pytest.fixture
def bluesky_storage(data_root) -> BlueskyStorageManager:
    return BlueskyStorageManager(StorageStage.RAW, VALID_DATASET_ID)


def write_stage_metadata(run_dir: Path, *, s3_upload_status: bool | None = True) -> Path:
    """Write a metadata.json under run_dir, omitting s3_upload_status entirely if None."""
    run_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {}
    if s3_upload_status is not None:
        payload["s3_upload_status"] = s3_upload_status
    path = run_dir / METADATA_FILENAME
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
