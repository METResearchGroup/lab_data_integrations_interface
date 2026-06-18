from __future__ import annotations

import shutil
from pathlib import Path

from data_platform.aws.constants import S3_BUCKET
from data_platform.aws.s3 import S3
from data_platform.postprocessing.constants import CURATED_S3_PREFIX
from data_platform.utils.storage import BlueskyStorageManager, StorageStage


def postprocess_bluesky(dataset_id: str, curated_path: Path) -> None:
    s3 = S3()
    _upload_curated(s3, dataset_id, curated_path)
    _delete_local(dataset_id)


def _upload_curated(s3: S3, dataset_id: str, curated_path: Path) -> None:
    run_dir = curated_path.parent
    for file in run_dir.iterdir():
        key = f"{CURATED_S3_PREFIX}/{dataset_id}/{file.name}"
        s3.upload_file(file, S3_BUCKET, key)


def _delete_local(dataset_id: str) -> None:
    dataset_dir = (
        BlueskyStorageManager(StorageStage.RAW, dataset_id).platform_data_root / dataset_id
    )
    shutil.rmtree(dataset_dir)
