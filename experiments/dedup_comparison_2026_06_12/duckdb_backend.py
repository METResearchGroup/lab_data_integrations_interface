"""DuckDB + S3 deduplication backend.

Workflow per pipeline run:
  1. check(): batch URIs loaded into an in-memory DuckDB table, JOINed against
              seen_uris S3 files read via httpfs — no S3 write for the batch,
              results return directly to Python memory (no intermediate file)
  2. write(): PUT new URIs as a text file to S3

No Athena, no DynamoDB, no intermediate result file, no cold start.
Compute runs locally in-process on the pipeline server using all available cores.

Run from repo root:
    PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/duckdb_backend.py
"""

from __future__ import annotations

import uuid

import boto3  # type: ignore[import-untyped]
import duckdb  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

BUCKET = "lab-data-integrations-dedup-experiment-use2"
S3_SEEN_PREFIX = "duckdb-dedup/seen_uris/"


class DuckDBBackend:
    def __init__(
        self,
        *,
        bucket: str = BUCKET,
        seen_prefix: str = S3_SEEN_PREFIX,
        region: str = "us-east-2",
    ) -> None:
        self._bucket = bucket
        self._seen_prefix = seen_prefix
        self._s3 = boto3.client("s3")
        self._last_written_key: str | None = None

        self._conn = duckdb.connect()
        self._conn.execute("INSTALL httpfs")
        self._conn.execute("LOAD httpfs")
        # Picks up credentials from env vars or ~/.aws/credentials automatically
        self._conn.execute(
            f"CREATE SECRET aws_secret (TYPE S3, PROVIDER CREDENTIAL_CHAIN, REGION '{region}')"
        )

    # ── helpers ───────────────────────────────────────────────────────────

    def _has_files(self) -> bool:
        resp = self._s3.list_objects_v2(Bucket=self._bucket, Prefix=self._seen_prefix, MaxKeys=1)
        return resp.get("KeyCount", 0) > 0

    def _put_uris(self, key: str, uris: list[str]) -> None:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body="\n".join(uris).encode())

    # ── DeduplicationBackend protocol ─────────────────────────────────────

    def seed(self, uris: list[str]) -> None:
        key = f"{self._seen_prefix}seed-{uuid.uuid4().hex}.txt"
        self._put_uris(key, uris)

    def check(self, uris: list[str]) -> tuple[list[str], int]:
        http_calls = 1  # S3 ListObjectsV2 for _has_files

        if not self._has_files():
            return uris, http_calls

        # Load batch into an in-memory table — no S3 write needed
        self._conn.execute("DROP TABLE IF EXISTS _batch")
        self._conn.execute("CREATE TABLE _batch (uri VARCHAR)")
        self._conn.executemany("INSERT INTO _batch VALUES (?)", [(u,) for u in uris])

        # DuckDB reads seen_uris files from S3 via httpfs, results go straight to memory
        s3_glob = f"s3://{self._bucket}/{self._seen_prefix}*.txt"
        rows = self._conn.execute(f"""
            SELECT b.uri
            FROM read_csv('{s3_glob}', header=false, columns={{'uri': 'VARCHAR'}}) s
            JOIN _batch b ON s.uri = b.uri
        """).fetchall()
        http_calls += 1  # logical S3 scan (actual GETs happen inside httpfs)

        already_seen = {row[0] for row in rows}
        new_uris = [u for u in uris if u not in already_seen]
        return new_uris, http_calls

    def write(self, uris: list[str]) -> int:
        if not uris:
            return 0
        key = f"{self._seen_prefix}run-{uuid.uuid4().hex}.txt"
        self._put_uris(key, uris)
        self._last_written_key = key
        return 1  # 1 S3 PUT

    def cleanup(self, uris: list[str]) -> None:  # noqa: ARG002  # uris not needed; tracked via _last_written_key
        if self._last_written_key:
            try:
                self._s3.delete_object(Bucket=self._bucket, Key=self._last_written_key)
            except ClientError:
                pass
            self._last_written_key = None

    def clear_all(self) -> None:
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._seen_prefix):
            objects = page.get("Contents", [])
            if objects:
                self._s3.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
                )


def self_check() -> None:
    import os

    if not os.environ.get("AWS_DEFAULT_REGION"):
        print("SKIP: AWS_DEFAULT_REGION not set")
        return

    backend = DuckDBBackend()
    backend.clear_all()
    backend.seed(["at://did:plc:abc/app.bsky.feed.post/001"])

    new_uris, _ = backend.check(
        [
            "at://did:plc:abc/app.bsky.feed.post/001",
            "at://did:plc:abc/app.bsky.feed.post/002",
        ]
    )
    assert new_uris == ["at://did:plc:abc/app.bsky.feed.post/002"], new_uris

    write_calls = backend.write(new_uris)
    assert write_calls == 1

    backend.cleanup(new_uris)
    new_uris2, _ = backend.check(["at://did:plc:abc/app.bsky.feed.post/002"])
    assert new_uris2 == ["at://did:plc:abc/app.bsky.feed.post/002"]

    backend.clear_all()
    print("DuckDBBackend SELF-CHECK PASS")


if __name__ == "__main__":
    self_check()
