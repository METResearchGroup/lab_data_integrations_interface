"""Export recent posts from the 250 most active Bluesky authors.

Queries ``bluesky_raw.posts`` once: authors with the most posts after
2026-08-01, then each author's 100 most recent posts. Writes
``posts.parquet`` beside this file.

Run from the repo root:

    PYTHONPATH=. uv run python \\
        experiments/grab_most_active_users_posts_2026_08_22/query_db.py
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
POSTS_AFTER_DATE = "2026-08-01"
TOP_USER_COUNT = 250
POSTS_PER_USER = 100

EXPERIMENT_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = EXPERIMENT_DIR / "posts.parquet"
S3_EXPORT_PREFIX = "athena-results/grab-most-active-users-posts-2026-08-22"


def build_unload_query(s3_uri: str) -> str:
    """Return the Athena UNLOAD that writes the experiment extract to S3."""

    return f"""
UNLOAD (
    WITH top_users AS (
        SELECT
            did,
            COUNT(*) AS user_post_count
        FROM posts
        WHERE created_at_day > DATE '{POSTS_AFTER_DATE}'
        GROUP BY did
        ORDER BY user_post_count DESC, did ASC
        LIMIT {TOP_USER_COUNT}
    ),
    ranked_posts AS (
        SELECT
            p.uri,
            p.did,
            p.cid,
            p.rev,
            CAST(p.created_at AS TIMESTAMP) AS created_at,
            CAST(p.ingested_at AS TIMESTAMP) AS ingested_at,
            p.run_id,
            p.text,
            p.langs,
            p.reply_root_uri,
            p.reply_parent_uri,
            p.embed_type,
            t.user_post_count,
            ROW_NUMBER() OVER (
                PARTITION BY p.did
                ORDER BY p.created_at DESC, p.uri DESC
            ) AS recency_rank
        FROM posts AS p
        INNER JOIN top_users AS t ON p.did = t.did
        WHERE p.created_at_day > DATE '{POSTS_AFTER_DATE}'
    )
    SELECT
        uri,
        did,
        cid,
        rev,
        created_at,
        ingested_at,
        run_id,
        text,
        langs,
        reply_root_uri,
        reply_parent_uri,
        embed_type,
        user_post_count,
        recency_rank
    FROM ranked_posts
    WHERE recency_rank <= {POSTS_PER_USER}
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
            local_path = dest / Path(key).name
            s3_client.download_file(bucket, key, str(local_path))
            downloaded.append(local_path)
    return downloaded


def _merge_parquet_files(parquet_paths: list[Path], output_path: Path) -> pa.Table:
    tables = [pq.read_table(path) for path in sorted(parquet_paths)]
    combined = pa.concat_tables(tables)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(combined, output_path, compression="zstd")
    return combined


def _print_extract_summary(table: pa.Table) -> None:
    frame = table.to_pandas()
    posts_per_user = frame.groupby("did").size()
    print(f"rows: {len(frame):,}")
    print(f"users: {frame['did'].nunique():,}")
    print(f"posts per user min/median/max: {posts_per_user.min()}/{posts_per_user.median():.0f}/{posts_per_user.max()}")
    print(f"wrote: {OUTPUT_PATH}")


def export_most_active_user_posts(athena: Athena, s3_client: boto3.client) -> Path:
    """Run the extract query and write ``posts.parquet`` next to this script."""

    if OUTPUT_PATH.exists():
        print(f"skipping, already exists at {OUTPUT_PATH}")
        return OUTPUT_PATH

    s3_uri = f"s3://{S3_BUCKET}/{S3_EXPORT_PREFIX}/"
    print(f"clearing {s3_uri}")
    _delete_s3_prefix(s3_client, S3_BUCKET, f"{S3_EXPORT_PREFIX}/")

    query = build_unload_query(s3_uri)
    print("running UNLOAD against bluesky_raw.posts")
    athena.run_query(query, database=GLUE_DATABASE, workgroup=WORKGROUP)

    with tempfile.TemporaryDirectory(prefix="most-active-posts-") as tmp_dir:
        parquet_files = _download_s3_prefix(
            s3_client, S3_BUCKET, f"{S3_EXPORT_PREFIX}/", Path(tmp_dir)
        )
        if not parquet_files:
            raise RuntimeError(f"UNLOAD produced no files under {s3_uri}")
        print(f"merging {len(parquet_files)} file(s)")
        table = _merge_parquet_files(parquet_files, OUTPUT_PATH)

    _delete_s3_prefix(s3_client, S3_BUCKET, f"{S3_EXPORT_PREFIX}/")
    _print_extract_summary(table)
    return OUTPUT_PATH


def main() -> None:
    print(f"database: {GLUE_DATABASE}")
    print(f"workgroup: {WORKGROUP}")
    print(f"filter: created_at_day > {POSTS_AFTER_DATE}")
    print(f"top users: {TOP_USER_COUNT}")
    print(f"posts per user: {POSTS_PER_USER}")
    print()
    export_most_active_user_posts(
        Athena(),
        boto3.client("s3", region_name=DEFAULT_REGION),
    )


if __name__ == "__main__":
    main()
