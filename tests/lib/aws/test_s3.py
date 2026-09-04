from __future__ import annotations

from lib.aws.s3 import S3


class FakeS3Client:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):  # noqa: N803
        self.calls.append(
            {"ClientMethod": ClientMethod, "Params": Params, "ExpiresIn": ExpiresIn}
        )
        return "https://signed.example/object"


class TestGeneratePresignedUrl:
    """Tests for S3.generate_presigned_url."""

    def test_presigns_bucket_and_key(self):
        client = FakeS3Client()
        s3 = S3(client=client)

        result = s3.generate_presigned_url("s3://bucket/path/key.parquet", 60)
        expected = "https://signed.example/object"

        assert result == expected
        assert client.calls == [
            {
                "ClientMethod": "get_object",
                "Params": {"Bucket": "bucket", "Key": "path/key.parquet"},
                "ExpiresIn": 60,
            }
        ]
