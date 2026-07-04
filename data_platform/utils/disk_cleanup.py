from __future__ import annotations

import shutil

from data_platform.utils.dataset import dataset_root
from data_platform.utils.gate_checks import require_dataset_fully_uploaded


def delete_dataset_local_files(platform: str, dataset_id: str) -> None:
    """Delete every local file for a dataset, once all stages are confirmed uploaded to S3.

    Raises via `require_dataset_fully_uploaded` instead of deleting anything if any stage's
    metadata.json isn't marked uploaded -- this is destructive and irreversible, so it must
    never run ahead of the S3 copy actually existing.
    """
    require_dataset_fully_uploaded(platform, dataset_id)
    root = dataset_root(platform, dataset_id)
    shutil.rmtree(root)
    print(f"delete_dataset_local_files: deleted {root}")
