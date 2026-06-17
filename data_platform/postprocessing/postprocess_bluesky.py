from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pandas as pd

from data_platform.aws.s3 import S3
from data_platform.postprocessing.constants import CURATED_S3_PREFIX, S3_BUCKET, URIS_S3_PREFIX
from data_platform.utils.storage import BlueskyStorageManager, StorageStage


def postprocess_bluesky(dataset_id: str, curated_path: Path) -> None:
    s3 = S3()
    _upload_curated(s3, dataset_id, curated_path)
    _upload_uris(s3, dataset_id, curated_path)
    _delete_local(dataset_id)


def _upload_curated(s3: S3, dataset_id: str, curated_path: Path) -> None:
    key = f"{CURATED_S3_PREFIX}/{dataset_id}/{curated_path.name}"
    s3.upload_file(curated_path, S3_BUCKET, key)


def _upload_uris(s3: S3, dataset_id: str, curated_path: Path) -> None:
    """Upload URIs from the curated output to S3. URIs are always uploaded as parquet."""
    uris = pd.read_parquet(curated_path, columns=["uri"])
    with tempfile.NamedTemporaryFile(suffix=".parquet") as tmp:
        tmp_path = Path(tmp.name)
        uris.to_parquet(tmp_path, index=False)
        key = f"{URIS_S3_PREFIX}/{dataset_id}/uris.parquet"
        s3.upload_file(tmp_path, S3_BUCKET, key)


def _delete_local(dataset_id: str) -> None:
    dataset_dir = (
        BlueskyStorageManager(StorageStage.RAW, dataset_id).platform_data_root / dataset_id
    )
    shutil.rmtree(dataset_dir)
