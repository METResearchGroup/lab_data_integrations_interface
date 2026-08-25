"""The slice of S3 that handing back a result file needs."""

from __future__ import annotations

import boto3

from bluesky_ingestion_jetstream.aws.constants import AWS_REGION


class S3:
    def __init__(self, region: str = AWS_REGION) -> None:
        self.client = boto3.client("s3", region_name=region)

    def generate_presigned_url(self, s3_uri: str, *, expires_in: int) -> str:
        """A download URL for an s3://bucket/key URI."""

        bucket, _, key = s3_uri.removeprefix("s3://").partition("/")
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
