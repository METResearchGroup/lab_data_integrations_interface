"""Shared S3 helper for presigning object download URLs."""

from __future__ import annotations

from lib.aws.clients import build_s3_client
from lib.aws.constants import AWS_REGION


class S3:
    """Presigns download URLs for s3://bucket/key URIs."""

    def __init__(self, region: str = AWS_REGION, client=None) -> None:
        self.client = client if client is not None else build_s3_client(region, None)

    def generate_presigned_url(self, s3_uri: str, expires_in: int) -> str:
        """Return a download URL for an s3://bucket/key URI."""

        raise NotImplementedError
