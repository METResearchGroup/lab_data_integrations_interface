"""
Sanity check for load_seen_ids_from_athena().

Steps:
  1. Uploads a parquet file with two fake URIs to the dedupe S3 path
  2. Registers the partition in Athena
  3. Calls load_seen_ids_from_athena() and asserts both IDs come back
  4. Cleans up the S3 file and Athena partition

Run from the project root:
  python -m data_platform.ingestion.sanity_checks.check_athena_dedupe
"""

from __future__ import annotations

import io
from typing import Any

import boto3
import pandas as pd

from data_platform.utils.storage import BlueskyStorageManager, StorageStage

BUCKET = "lab-data-integrations-interface"
PLATFORM = "bluesky"
TEST_DATASET_ID = "sanity_check_dataset"
S3_KEY = f"dedupe/platform={PLATFORM}/dataset_id={TEST_DATASET_ID}/seen_ids.parquet"
ATHENA_DB = "lab_data_integrations_interface"
ATHENA_TABLE = "dedupe_seen_ids"
WORKGROUP = "lab-data-integrations-interface"
FAKE_IDS = {"at://did:plc:sanity/check/001", "at://did:plc:sanity/check/002"}


def upload_test_file(s3: Any) -> None:
    buf = io.BytesIO()
    pd.DataFrame({"id": sorted(FAKE_IDS)}).to_parquet(buf, index=False)
    buf.seek(0)
    s3.put_object(Bucket=BUCKET, Key=S3_KEY, Body=buf.read())
    print(f"  uploaded s3://{BUCKET}/{S3_KEY}")


def register_partition(athena: Any) -> None:
    sql = (
        f"ALTER TABLE {ATHENA_TABLE} ADD IF NOT EXISTS "
        f"PARTITION (platform='{PLATFORM}', dataset_id='{TEST_DATASET_ID}') "
        f"LOCATION 's3://{BUCKET}/dedupe/platform={PLATFORM}/dataset_id={TEST_DATASET_ID}/'"
    )
    _run_athena_ddl(athena, sql)
    print(f"  registered partition platform={PLATFORM}/dataset_id={TEST_DATASET_ID}")


def drop_partition(athena: Any) -> None:
    sql = (
        f"ALTER TABLE {ATHENA_TABLE} DROP IF EXISTS "
        f"PARTITION (platform='{PLATFORM}', dataset_id='{TEST_DATASET_ID}')"
    )
    _run_athena_ddl(athena, sql)
    print(f"  dropped partition platform={PLATFORM}/dataset_id={TEST_DATASET_ID}")


def delete_test_file(s3: Any) -> None:
    s3.delete_object(Bucket=BUCKET, Key=S3_KEY)
    print(f"  deleted s3://{BUCKET}/{S3_KEY}")


def _run_athena_ddl(athena: Any, sql: str) -> None:
    import time

    response = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": ATHENA_DB},
        WorkGroup=WORKGROUP,
    )
    execution_id = response["QueryExecutionId"]
    while True:
        state = athena.get_query_execution(QueryExecutionId=execution_id)
        status = state["QueryExecution"]["Status"]["State"]
        if status == "SUCCEEDED":
            break
        if status in ("FAILED", "CANCELLED"):
            reason = state["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
            raise RuntimeError(f"DDL query {status}: {reason}")
        time.sleep(1)


def main() -> None:
    s3 = boto3.client("s3", region_name="us-east-2")
    athena = boto3.client("athena", region_name="us-east-2")
    storage = BlueskyStorageManager(
        StorageStage.RAW, "bluesky_00000000-0000-4000-8000-000000000001"
    )

    print("--- setup ---")
    upload_test_file(s3)
    register_partition(athena)

    print("--- querying ---")
    seen = storage.load_seen_ids_from_athena()
    print(f"  load_seen_ids_from_athena() returned: {seen}")

    missing = FAKE_IDS - seen
    assert not missing, f"expected IDs not returned: {missing}"
    print("  PASS: all expected IDs returned")

    print("--- cleanup ---")
    drop_partition(athena)
    delete_test_file(s3)
    print("done")


if __name__ == "__main__":
    main()
