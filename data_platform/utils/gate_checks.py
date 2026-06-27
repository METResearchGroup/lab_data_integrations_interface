from __future__ import annotations

from data_platform.generate_features.models import FeatureRunMetadata
from data_platform.utils.storage import StorageManager


def require_all_runs_uploaded(storage: StorageManager, dataset_id: str) -> None:
    if not storage.all_runs_uploaded():
        raise RuntimeError(
            f"Not all {storage.stage} runs for dataset {dataset_id} have been uploaded to S3"
        )


def require_features_uploaded(meta: FeatureRunMetadata, dataset_id: str) -> None:
    if not meta.s3_upload_status:
        raise RuntimeError(f"Features for dataset {dataset_id} have not been uploaded to S3")
