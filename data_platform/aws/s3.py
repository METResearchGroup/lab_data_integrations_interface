from __future__ import annotations

from pathlib import Path

import boto3

from data_platform.aws.constants import DEFAULT_REGION


class S3:
    def __init__(self, region: str = DEFAULT_REGION) -> None:
        self.client = boto3.client("s3", region_name=region)

    def generate_presigned_url(self, s3_uri: str, expires_in: int = 86400) -> str:
        """Generate a presigned download URL for an S3 URI (s3://bucket/key)."""
        without_scheme = s3_uri.removeprefix("s3://")
        bucket, _, key = without_scheme.partition("/")
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def upload_file(self, local_path: Path, bucket: str, key: str) -> None:
        """Upload a file to S3. Raises S3UploadFailedError on failure — no explicit handling needed,
        callers rely on the exception propagating to abort downstream steps (e.g. local cleanup).
        Logging will be done at the orchestration layer (prefect) instead of here."""
        self.client.upload_file(str(local_path), bucket, key)
