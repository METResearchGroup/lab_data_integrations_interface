"""Athena + S3 deduplication backend.

Workflow per pipeline run:
  1. check(): PUT batch URIs as a temp S3 file, run a single Athena JOIN query
              against seen_uris, DELETE the temp file
  2. write(): PUT new URIs as a text file to S3 — no Athena needed

No DynamoDB required. Always exactly 1 Athena query per check() regardless of
batch size, because URIs are passed via S3 file rather than the SQL string.

Run from repo root:
    PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/athena_backend.py
"""

from __future__ import annotations

import time
import uuid

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

BUCKET = "lab-data-integrations-dedup-experiment-use2"
S3_SEEN_PREFIX = "athena-dedup/seen_uris/"
S3_BATCH_PREFIX = "athena-dedup/batch_temp/"
S3_RESULTS_PREFIX = "athena-dedup/results/"
ATHENA_DATABASE = "lab_data_integrations_dedup_experiment"
SEEN_TABLE = "seen_uris"
BATCH_TABLE = "batch_input"

# In production the pipeline runs every few hours, so Presto workers are always
# fully spun down between runs. Every check() is a cold start.
# Measured in this experiment: first query 4894ms vs warm baseline ~1700ms.
# Cold start overhead ≈ 3200ms on top of warm execution time.
ATHENA_COLD_START_OVERHEAD_MS = 3200

_POLL_INTERVAL_S = 0.1
_TABLE_DDL = (
    "ROW FORMAT DELIMITED FIELDS TERMINATED BY '\\t' LINES TERMINATED BY '\\n' STORED AS TEXTFILE"
)


class AthenaBackend:
    def __init__(
        self,
        *,
        bucket: str = BUCKET,
        seen_prefix: str = S3_SEEN_PREFIX,
        batch_prefix: str = S3_BATCH_PREFIX,
        results_prefix: str = S3_RESULTS_PREFIX,
        database: str = ATHENA_DATABASE,
    ) -> None:
        self._bucket = bucket
        self._seen_prefix = seen_prefix
        self._batch_prefix = batch_prefix
        self._results_prefix = results_prefix
        self._database = database
        self._s3 = boto3.client("s3")
        self._athena = boto3.client("athena")
        self._last_written_key: str | None = None
        self._table_ready = False

    # ── setup ─────────────────────────────────────────────────────────────

    def _ensure_tables(self) -> None:
        if self._table_ready:
            return
        self._execute_query(
            f"CREATE DATABASE IF NOT EXISTS {self._database}",
            database=None,
        )
        self._execute_query(
            f"""
            CREATE EXTERNAL TABLE IF NOT EXISTS {SEEN_TABLE} (uri STRING)
            {_TABLE_DDL}
            LOCATION 's3://{self._bucket}/{self._seen_prefix}'
            """,
            database=self._database,
        )
        self._execute_query(
            f"""
            CREATE EXTERNAL TABLE IF NOT EXISTS {BATCH_TABLE} (uri STRING)
            {_TABLE_DDL}
            LOCATION 's3://{self._bucket}/{self._batch_prefix}'
            """,
            database=self._database,
        )
        self._table_ready = True

    # ── Athena internals ──────────────────────────────────────────────────

    def _execute_query(self, sql: str, *, database: str | None) -> tuple[str, int]:
        """Submit a query, poll to completion, return (execution_id, http_call_count)."""
        kwargs: dict = {
            "QueryString": sql,
            "ResultConfiguration": {
                "OutputLocation": f"s3://{self._bucket}/{self._results_prefix}"
            },
        }
        if database:
            kwargs["QueryExecutionContext"] = {"Database": database}

        resp = self._athena.start_query_execution(**kwargs)
        execution_id = resp["QueryExecutionId"]
        http_calls = 1  # start_query_execution

        while True:
            status = self._athena.get_query_execution(QueryExecutionId=execution_id)
            http_calls += 1
            state = status["QueryExecution"]["Status"]["State"]
            if state == "SUCCEEDED":
                return execution_id, http_calls
            if state in ("FAILED", "CANCELLED"):
                reason = status["QueryExecution"]["Status"].get("StateChangeReason", "")
                raise RuntimeError(f"Athena query {state}: {reason}\nSQL: {sql[:300]}")
            time.sleep(_POLL_INTERVAL_S)

    def _read_single_column(self, execution_id: str) -> list[str]:
        """Read all rows from a completed single-column Athena query result."""
        results: list[str] = []
        paginator = self._athena.get_paginator("get_query_results")
        for page_num, page in enumerate(paginator.paginate(QueryExecutionId=execution_id)):
            rows = page["ResultSet"]["Rows"]
            start = 1 if page_num == 0 else 0  # skip header row on first page only
            for row in rows[start:]:
                val = row["Data"][0].get("VarCharValue", "")
                if val:
                    results.append(val)
        return results

    def _put_uris(self, key: str, uris: list[str]) -> None:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body="\n".join(uris).encode())

    # ── DeduplicationBackend protocol ─────────────────────────────────────

    def seed(self, uris: list[str]) -> None:
        self._ensure_tables()
        key = f"{self._seen_prefix}seed-{uuid.uuid4().hex}.txt"
        self._put_uris(key, uris)

    def check(self, uris: list[str]) -> tuple[list[str], int]:
        self._ensure_tables()

        # Upload batch as temp file — Athena reads it via batch_input table
        batch_key = f"{self._batch_prefix}batch.txt"
        self._put_uris(batch_key, uris)
        http_calls = 1  # S3 PUT

        try:
            sql = f"SELECT s.uri FROM {SEEN_TABLE} s JOIN {BATCH_TABLE} b ON s.uri = b.uri"
            execution_id, query_calls = self._execute_query(sql, database=self._database)
            http_calls += query_calls
            already_seen = set(self._read_single_column(execution_id))
        finally:
            self._s3.delete_object(Bucket=self._bucket, Key=batch_key)
            http_calls += 1  # S3 DELETE

        new_uris = [u for u in uris if u not in already_seen]
        return new_uris, http_calls

    def write(self, uris: list[str]) -> int:
        if not uris:
            return 0
        key = f"{self._seen_prefix}run-{uuid.uuid4().hex}.txt"
        self._put_uris(key, uris)
        self._last_written_key = key
        return 1  # 1 S3 PUT

    def cleanup(self, uris: list[str]) -> None:  # noqa: ARG002
        """Delete the file written by the last write() call (resets between benchmark runs)."""
        if self._last_written_key:
            try:
                self._s3.delete_object(Bucket=self._bucket, Key=self._last_written_key)
            except ClientError:
                pass
            self._last_written_key = None

    def clear_all(self) -> None:
        for prefix in (self._seen_prefix, self._batch_prefix):
            paginator = self._s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
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

    backend = AthenaBackend()
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
    print("AthenaBackend SELF-CHECK PASS")


if __name__ == "__main__":
    self_check()
