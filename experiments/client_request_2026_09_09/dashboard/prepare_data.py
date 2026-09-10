"""Build gzipped JSON for the candidate post explorer and upload it to S3.

Run from the repo root:

    PYTHONPATH=. uv run python \\
        experiments/client_request_2026_09_09/dashboard/prepare_data.py
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import boto3
import pyarrow.parquet as pq

from experiments.client_request_2026_09_09.constants import (
    CANDIDATES,
    JSON_INDENT,
    S3_BUCKET,
    S3_PREFIX,
    UTF8_ENCODING,
    s3_object_uri,
)
from experiments.client_request_2026_09_09.urls import bsky_post_url
from lib.aws.constants import AWS_REGION

RUN_TIMESTAMP = "2026_09_10-15:22:35"
DASHBOARD_DIR = Path(__file__).resolve().parent
LOCAL_PARQUET_DIR = DASHBOARD_DIR.parent / "data" / RUN_TIMESTAMP
LOCAL_JSON_DIR = DASHBOARD_DIR / "data"
CONFIG_PATH = DASHBOARD_DIR / "config.js"
S3_DASHBOARD_PREFIX = f"{S3_PREFIX}/{RUN_TIMESTAMP}/dashboard"
GZIP_LEVEL = 9


def serialize_row(row: dict) -> dict:
    """Turn one Parquet row into a JSON object for the explorer."""

    created_at = row["created_at"]
    if hasattr(created_at, "isoformat"):
        created_at_text = created_at.isoformat()
    else:
        created_at_text = str(created_at)
    uri = str(row["uri"])
    return {
        "uri": uri,
        "did": str(row["did"]),
        "text": str(row["text"]),
        "created_at": created_at_text,
        "matched_candidate": str(row["matched_candidate"]),
        "matched_name_string": str(row["matched_name_string"]),
        "bsky_url": row.get("url") or bsky_post_url(uri),
    }


def rows_from_parquet(path: Path) -> list[dict]:
    """Load a candidate Parquet file and serialize every row."""

    table = pq.read_table(path)
    return [serialize_row(row) for row in table.to_pylist()]


def write_gzip_json(path: Path, rows: list[dict]) -> int:
    """Write ``rows`` as gzipped minified JSON. Returns uncompressed byte count."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(rows, separators=(",", ":")).encode(UTF8_ENCODING)
    path.write_bytes(gzip.compress(payload, compresslevel=GZIP_LEVEL))
    return len(payload)


def ensure_get_cors(s3_client) -> None:
    """Allow browser GET of presigned objects from any origin."""

    s3_client.put_bucket_cors(
        Bucket=S3_BUCKET,
        CORSConfiguration={
            "CORSRules": [
                {
                    "AllowedMethods": ["GET", "HEAD"],
                    "AllowedOrigins": ["*"],
                    "AllowedHeaders": ["*"],
                    "ExposeHeaders": ["ETag", "Content-Length", "Content-Type"],
                    "MaxAgeSeconds": 3600,
                }
            ]
        },
    )


def _config_js(sources: list[dict]) -> str:
    body = json.dumps(
        {
            "runTimestamp": RUN_TIMESTAMP,
            "postsParquet": s3_object_uri(
                f"{S3_PREFIX}/{RUN_TIMESTAMP}/posts.parquet"
            ),
            "candidates": sources,
        },
        indent=JSON_INDENT,
    )
    return f"window.DASHBOARD_CONFIG = {body};\n"


def main() -> None:
    """Write local gzip JSON, upload it, and emit config.js with relative URLs."""

    s3_client = boto3.client("s3", region_name=AWS_REGION)
    ensure_get_cors(s3_client)
    sources: list[dict] = []
    LOCAL_JSON_DIR.mkdir(parents=True, exist_ok=True)

    for candidate in CANDIDATES:
        parquet_path = LOCAL_PARQUET_DIR / f"{candidate.candidate_id}.parquet"
        rows = rows_from_parquet(parquet_path)
        gzip_name = f"{candidate.candidate_id}.json.gz"
        local_gzip = LOCAL_JSON_DIR / gzip_name
        uncompressed = write_gzip_json(local_gzip, rows)
        object_key = f"{S3_DASHBOARD_PREFIX}/{gzip_name}"
        s3_client.upload_file(
            str(local_gzip),
            S3_BUCKET,
            object_key,
            ExtraArgs={"ContentType": "application/gzip"},
        )
        sources.append(
            {
                "candidateId": candidate.candidate_id,
                "displayName": candidate.display_name,
                "rowCount": len(rows),
                "url": f"data/{gzip_name}",
            }
        )
        print(
            f"{candidate.candidate_id}: {len(rows)} rows, "
            f"{uncompressed} json bytes -> s3://{S3_BUCKET}/{object_key}"
        )

    CONFIG_PATH.write_text(_config_js(sources), encoding=UTF8_ENCODING)
    print(f"wrote {CONFIG_PATH}")


if __name__ == "__main__":
    main()
