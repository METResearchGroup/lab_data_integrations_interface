from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from data_platform.aws.constants import S3_BUCKET
from data_platform.aws.s3 import S3
from data_platform.utils.storage import BlueskyStorageManager

DEDUPE_S3_PREFIX = "dedupe"


def upload_seen_uris(dataset_id: str, run_dir: Path, storage: BlueskyStorageManager) -> None:
    seen_uris = storage.load_seen_ids_from_disk(run_dir, "uri")
    df = pd.DataFrame({"id": list(seen_uris)})
    with tempfile.NamedTemporaryFile(suffix=".parquet") as tmp:
        tmp_path = Path(tmp.name)
        df.to_parquet(tmp_path, index=False)
        key = f"{DEDUPE_S3_PREFIX}/platform=bluesky/dataset_id={dataset_id}/seen_ids.parquet"
        S3().upload_file(tmp_path, S3_BUCKET, key)
