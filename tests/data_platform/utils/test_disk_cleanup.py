from __future__ import annotations

from pathlib import Path

import pytest

from data_platform.utils.dataset import dataset_root
from data_platform.utils.disk_cleanup import delete_dataset_local_files
from data_platform.utils.storage import BlueskyStorageManager, StorageStage
from tests.data_platform.constants import VALID_DATASET_ID
from tests.data_platform.utils.conftest import write_stage_metadata


def test_delete_dataset_local_files_removes_directory_when_fully_uploaded(data_root: Path) -> None:
    curated = BlueskyStorageManager(StorageStage.CURATED, VALID_DATASET_ID)
    write_stage_metadata(curated.create_new_run_dir("2026_01_01-00:10:00"), s3_upload_status=True)
    root = dataset_root("bluesky", VALID_DATASET_ID)
    assert root.exists()

    delete_dataset_local_files("bluesky", VALID_DATASET_ID)

    assert not root.exists()


def test_delete_dataset_local_files_raises_and_preserves_files_when_not_uploaded(
    data_root: Path,
) -> None:
    curated = BlueskyStorageManager(StorageStage.CURATED, VALID_DATASET_ID)
    run_dir = curated.create_new_run_dir("2026_01_01-00:10:00")
    write_stage_metadata(run_dir, s3_upload_status=False)
    root = dataset_root("bluesky", VALID_DATASET_ID)

    with pytest.raises(RuntimeError, match=VALID_DATASET_ID):
        delete_dataset_local_files("bluesky", VALID_DATASET_ID)

    assert root.exists()
    assert (run_dir / "metadata.json").exists()


def test_delete_dataset_local_files_raises_file_not_found_when_dataset_root_missing(
    data_root: Path,
) -> None:
    """Documents current behavior: a missing dataset root vacuously passes the upload
    gate, so shutil.rmtree's own FileNotFoundError surfaces -- there's no special-case
    handling for "nothing to delete" in delete_dataset_local_files itself."""
    with pytest.raises(FileNotFoundError):
        delete_dataset_local_files("bluesky", VALID_DATASET_ID)
