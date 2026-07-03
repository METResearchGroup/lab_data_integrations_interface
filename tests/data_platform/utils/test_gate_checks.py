from __future__ import annotations

from pathlib import Path

import pytest

from data_platform.utils.dataset import dataset_root
from data_platform.utils.gate_checks import require_dataset_fully_uploaded
from data_platform.utils.storage import BlueskyStorageManager, StorageStage
from tests.data_platform.constants import VALID_DATASET_ID
from tests.data_platform.utils.conftest import write_stage_metadata


def test_require_dataset_fully_uploaded_passes_when_dataset_root_missing(data_root: Path) -> None:
    require_dataset_fully_uploaded("bluesky", VALID_DATASET_ID)


def test_require_dataset_fully_uploaded_passes_when_no_metadata_files_found(
    data_root: Path,
) -> None:
    dataset_root("bluesky", VALID_DATASET_ID).mkdir(parents=True)

    require_dataset_fully_uploaded("bluesky", VALID_DATASET_ID)


def test_require_dataset_fully_uploaded_passes_when_all_metadata_uploaded(data_root: Path) -> None:
    raw = BlueskyStorageManager(StorageStage.RAW, VALID_DATASET_ID)
    preprocessed = BlueskyStorageManager(StorageStage.PREPROCESSED, VALID_DATASET_ID)
    curated = BlueskyStorageManager(StorageStage.CURATED, VALID_DATASET_ID)
    write_stage_metadata(raw.create_new_run_dir("2026_01_01-00:00:00"), s3_upload_status=True)
    write_stage_metadata(
        preprocessed.create_new_run_dir("2026_01_01-00:05:00"), s3_upload_status=True
    )
    write_stage_metadata(curated.create_new_run_dir("2026_01_01-00:10:00"), s3_upload_status=True)
    write_stage_metadata(
        dataset_root("bluesky", VALID_DATASET_ID) / "features", s3_upload_status=True
    )

    require_dataset_fully_uploaded("bluesky", VALID_DATASET_ID)


def test_require_dataset_fully_uploaded_raises_when_metadata_not_uploaded(data_root: Path) -> None:
    curated = BlueskyStorageManager(StorageStage.CURATED, VALID_DATASET_ID)
    write_stage_metadata(curated.create_new_run_dir("2026_01_01-00:10:00"), s3_upload_status=False)

    with pytest.raises(RuntimeError, match=VALID_DATASET_ID):
        require_dataset_fully_uploaded("bluesky", VALID_DATASET_ID)


def test_require_dataset_fully_uploaded_raises_when_s3_upload_status_key_missing(
    data_root: Path,
) -> None:
    curated = BlueskyStorageManager(StorageStage.CURATED, VALID_DATASET_ID)
    write_stage_metadata(curated.create_new_run_dir("2026_01_01-00:10:00"), s3_upload_status=None)

    with pytest.raises(RuntimeError, match=VALID_DATASET_ID):
        require_dataset_fully_uploaded("bluesky", VALID_DATASET_ID)


def test_require_dataset_fully_uploaded_raises_when_older_run_dir_not_uploaded(
    data_root: Path,
) -> None:
    """A later run dir being uploaded must not mask an earlier, still-unuploaded one --
    every run dir for every stage has to check out, not just the latest."""
    raw = BlueskyStorageManager(StorageStage.RAW, VALID_DATASET_ID)
    older_run = raw.create_new_run_dir("2026_01_01-00:00:00")
    newer_run = raw.create_new_run_dir("2026_01_02-00:00:00")
    write_stage_metadata(older_run, s3_upload_status=False)
    write_stage_metadata(newer_run, s3_upload_status=True)

    with pytest.raises(RuntimeError, match=VALID_DATASET_ID):
        require_dataset_fully_uploaded("bluesky", VALID_DATASET_ID)
