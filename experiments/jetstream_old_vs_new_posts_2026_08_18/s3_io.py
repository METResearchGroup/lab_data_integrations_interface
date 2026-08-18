"""S3 listing, download, and year-prefix inventory for the posts warehouse."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import boto3
from botocore.client import BaseClient

from experiments.jetstream_old_vs_new_posts_2026_08_18.constants import (
    AWS_REGION,
    INVENTORY_YEARS,
    POSTS_DATA_PREFIX,
    S3_BUCKET,
)


def s3_client() -> BaseClient:
    return boto3.client("s3", region_name=AWS_REGION)


def download_key(client: BaseClient, key: str, dest: Path) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    head = client.head_object(Bucket=S3_BUCKET, Key=key)
    client.download_file(S3_BUCKET, key, str(dest))
    return {
        "key": key,
        "bytes": head["ContentLength"],
        "last_modified": _iso(head["LastModified"]),
        "local_path": str(dest),
    }


def iter_objects(client: BaseClient, prefix: str) -> Iterator[dict[str, Any]]:
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        yield from page.get("Contents") or []


def inventory_year(client: BaseClient, year: int) -> dict[str, Any]:
    prefix = f"{POSTS_DATA_PREFIX}created_at_day={year}-"
    n_files = 0
    total_bytes = 0
    days: set[str] = set()
    write_ids: set[str] = set()
    first: datetime | None = None
    last: datetime | None = None

    for obj in iter_objects(client, prefix):
        n_files += 1
        total_bytes += obj["Size"]
        key: str = obj["Key"]
        day = _partition_day(key)
        if day is not None:
            days.add(day)
        write_id = _write_uuid(key)
        if write_id is not None:
            write_ids.add(write_id)
        modified = obj["LastModified"]
        first = modified if first is None else min(first, modified)
        last = modified if last is None else max(last, modified)

    return {
        "year": year,
        "prefix": prefix,
        "n_files": n_files,
        "total_bytes": total_bytes,
        "n_days": len(days),
        "n_write_uuids": len(write_ids),
        "first_modified": _iso(first) if first else None,
        "last_modified": _iso(last) if last else None,
    }


def inventory_years(client: BaseClient) -> list[dict[str, Any]]:
    return [inventory_year(client, year) for year in INVENTORY_YEARS]


def list_parquet_keys(client: BaseClient, prefix: str) -> list[str]:
    return [obj["Key"] for obj in iter_objects(client, prefix) if obj["Key"].endswith(".parquet")]


def _partition_day(key: str) -> str | None:
    for part in key.split("/"):
        if part.startswith("created_at_day="):
            return part.split("=", 1)[1]
    return None


def _write_uuid(key: str) -> str | None:
    """Iceberg names files `{seq}-{partition_id}-{uuid}.parquet`."""

    stem = key.rsplit("/", 1)[-1].removesuffix(".parquet")
    parts = stem.split("-")
    if len(parts) < 7:
        return None
    return "-".join(parts[2:])


def _iso(value: datetime) -> str:
    return value.isoformat()
