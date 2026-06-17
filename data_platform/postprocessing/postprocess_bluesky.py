from __future__ import annotations

import shutil
from pathlib import Path

from data_platform.aws.s3 import S3
from data_platform.utils.storage import BlueskyStorageManager, StorageStage

S3_BUCKET = ""  # TODO
CURATED_S3_PREFIX = "bluesky/curated"
URIS_S3_PREFIX = "bluesky/uris"


def postprocess_bluesky(dataset_id: str, curated_path: Path) -> None:
    s3 = S3()
    _upload_curated(s3, dataset_id, curated_path)
    _upload_uris(s3, dataset_id)
    _delete_local(dataset_id)


def _upload_curated(s3: S3, dataset_id: str, curated_path: Path) -> None:
    key = f"{CURATED_S3_PREFIX}/{dataset_id}/{curated_path.name}"
    s3.upload_file(curated_path, S3_BUCKET, key)


def _upload_uris(s3: S3, dataset_id: str) -> None:
    # TODO: determine URI source and S3 key
    raise NotImplementedError


def _delete_local(dataset_id: str) -> None:
    dataset_dir = (
        BlueskyStorageManager(StorageStage.RAW, dataset_id).platform_data_root / dataset_id
    )
    shutil.rmtree(dataset_dir)
