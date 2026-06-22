from __future__ import annotations

from pathlib import Path

import boto3

from data_platform.aws.constants import DEFAULT_REGION


class S3:
    def __init__(self, region: str = DEFAULT_REGION) -> None:
        self.client = boto3.client("s3", region_name=region)

    def upload_file(self, local_path: Path, bucket: str, key: str) -> None:
        """Upload a file to S3. Raises S3UploadFailedError on failure — no explicit handling needed,
        callers rely on the exception propagating to abort downstream steps (e.g. local cleanup).
        Logging will be done at the orchestration layer (prefect) instead of here."""
        self.client.upload_file(str(local_path), bucket, key)
