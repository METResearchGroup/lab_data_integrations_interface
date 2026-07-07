from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_platform.utils.dataset import dataset_root
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


def seed_fully_uploaded_dataset() -> Path:
    """Write real, fully-uploaded metadata.json files for every stage of the bluesky
    VALID_DATASET_ID dataset, so gate-check/cleanup/orchestration tests have genuine
    files on disk to check and delete. Requires the data_root fixture to be active."""
    for stage in (StorageStage.RAW, StorageStage.PREPROCESSED, StorageStage.CURATED):
        storage = BlueskyStorageManager(stage, VALID_DATASET_ID)
        write_stage_metadata(
            storage.create_new_run_dir("2026_01_01-00:00:00"), s3_upload_status=True
        )
    write_stage_metadata(
        dataset_root("bluesky", VALID_DATASET_ID) / StorageStage.FEATURES, s3_upload_status=True
    )
    return dataset_root("bluesky", VALID_DATASET_ID)
