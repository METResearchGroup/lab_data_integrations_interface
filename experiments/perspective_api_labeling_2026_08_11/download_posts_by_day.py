"""Download Bluesky posts for selected days from Athena into local Parquet files.

Runs one SELECT * per day via Athena UNLOAD (Parquet on S3), then merges the
exported files into a single local Parquet file per day.

Run from repo root:

    PYTHONPATH=. uv run python \\
        experiments/perspective_api_labeling_2026_08_11/download_posts_by_day.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import boto3
import pyarrow as pa
import pyarrow.parquet as pq

from data_platform.aws.athena import Athena
from data_platform.aws.constants import DEFAULT_REGION, S3_BUCKET

GLUE_DATABASE = "bluesky_raw"
WORKGROUP = "bluesky_raw_maintenance"
DAYS = ("2026-08-09", "2026-08-10")

DATA_DIR = Path(__file__).resolve().parent / "data"
S3_EXPORT_PREFIX = "athena-results/perspective-api-labeling"


def _build_unload_query(day: str) -> str:
    s3_uri = f"s3://{S3_BUCKET}/{S3_EXPORT_PREFIX}/{day}/"
    return f"""
UNLOAD (
    SELECT *
    FROM posts
    WHERE CAST(created_at AS DATE) = DATE '{day}'
)
TO '{s3_uri}'
WITH (format = 'PARQUET', compression = 'ZSTD')
"""


def _delete_s3_prefix(s3_client: boto3.client, bucket: str, prefix: str) -> None:
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = page.get("Contents", [])
        if not objects:
            continue
        s3_client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
        )


def _download_s3_prefix(
    s3_client: boto3.client, bucket: str, prefix: str, dest: Path
) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            filename = Path(key).name
            local_path = dest / filename
            s3_client.download_file(bucket, key, str(local_path))
            downloaded.append(local_path)
    return downloaded


def _merge_parquet_files(parquet_paths: list[Path], output_path: Path) -> int:
    tables = [pq.read_table(path) for path in sorted(parquet_paths)]
    combined = pa.concat_tables(tables)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(combined, output_path, compression="zstd")
    return combined.num_rows


def download_day(day: str, *, athena: Athena, s3_client: boto3.client) -> Path:
    output_path = DATA_DIR / f"{day}.parquet"
    if output_path.exists():
        print(f"{day}: skipping, already exists at {output_path}")
        return output_path

    s3_prefix = f"{S3_EXPORT_PREFIX}/{day}/"
    print(f"{day}: clearing s3://{S3_BUCKET}/{s3_prefix}")
    _delete_s3_prefix(s3_client, S3_BUCKET, s3_prefix)

    query = _build_unload_query(day)
    print(f"{day}: running UNLOAD (SELECT * ...)")
    athena.run_query(query, database=GLUE_DATABASE, workgroup=WORKGROUP)

    with tempfile.TemporaryDirectory(prefix=f"posts-{day}-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        print(f"{day}: downloading exported Parquet from S3")
        parquet_files = _download_s3_prefix(s3_client, S3_BUCKET, s3_prefix, tmp_path)
        if not parquet_files:
            raise RuntimeError(
                f"{day}: UNLOAD produced no files under s3://{S3_BUCKET}/{s3_prefix}"
            )

        print(f"{day}: merging {len(parquet_files)} file(s) -> {output_path}")
        row_count = _merge_parquet_files(parquet_files, output_path)
        print(f"{day}: wrote {row_count:,} rows")

    print(f"{day}: cleaning up S3 export prefix")
    _delete_s3_prefix(s3_client, S3_BUCKET, s3_prefix)
    return output_path


def main() -> None:
    athena = Athena()
    s3_client = boto3.client("s3", region_name=DEFAULT_REGION)

    print(f"database: {GLUE_DATABASE}")
    print(f"workgroup: {WORKGROUP}")
    print(f"output dir: {DATA_DIR}")
    print()

    for day in DAYS:
        download_day(day, athena=athena, s3_client=s3_client)
        print()


if __name__ == "__main__":
    main()
