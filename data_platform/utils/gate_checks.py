from __future__ import annotations

import json

from data_platform.generate_features.models import FeatureRunMetadata
from data_platform.utils.dataset import dataset_root
from data_platform.utils.storage import METADATA_FILENAME, StorageManager


def require_all_runs_uploaded(storage: StorageManager, dataset_id: str) -> None:
    if not storage.all_runs_uploaded():
        raise RuntimeError(
            f"Not all {storage.stage} runs for dataset {dataset_id} have been uploaded to S3"
        )


def require_features_uploaded(meta: FeatureRunMetadata, dataset_id: str) -> None:
    if not meta.s3_upload_status:
        raise RuntimeError(f"Features for dataset {dataset_id} have not been uploaded to S3")


def require_dataset_fully_uploaded(platform: str, dataset_id: str) -> None:
    """Raise if any stage's metadata.json for this dataset is not marked uploaded to S3.

    Walks every metadata.json under the dataset root -- across all stages (raw,
    preprocessed, features, curated) and every timestamped run dir within each stage --
    rather than checking one stage at a time, since it's meant to gate whole-dataset local
    disk cleanup: every stage must be confirmed durable in S3 before local files are safe
    to delete.
    """
    root = dataset_root(platform, dataset_id)
    if not root.exists():
        return
    for metadata_path in root.rglob(METADATA_FILENAME):
        with metadata_path.open(encoding="utf-8") as f:
            metadata = json.load(f)
        if not metadata.get("s3_upload_status", False):
            raise RuntimeError(
                f"{metadata_path.relative_to(root)} for dataset {dataset_id} "
                "has not been uploaded to S3"
            )
