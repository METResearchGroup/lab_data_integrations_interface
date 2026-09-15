"""Write buffered rows as Parquet under the landing prefix."""

from datetime import datetime
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
from pyarrow.fs import FileSystem, S3FileSystem

from bluesky_backfill_app.fetch_repos.constants import LANDING_ROOT
from bluesky_backfill_app.fetch_repos.storage.buffer import RepoBuffer
from bluesky_ingestion_jetstream.aws.constants import (
    S3_CONNECT_TIMEOUT_SECONDS,
    S3_REQUEST_TIMEOUT_SECONDS,
)
from bluesky_ingestion_jetstream.constants import RecordType
from bluesky_ingestion_jetstream.schemas.arrow_schemas import RECORD_TYPE_TO_SCHEMA
from lib.aws.constants import AWS_REGION
from lib.timestamp_utils import CREATED_AT_FORMAT, get_current_timestamp


def build_filesystem() -> S3FileSystem:
    return S3FileSystem(
        region=AWS_REGION,
        connect_timeout=S3_CONNECT_TIMEOUT_SECONDS,
        request_timeout=S3_REQUEST_TIMEOUT_SECONDS,
    )


def build_path(
    record_type: RecordType,
    run_id: str,
    timestamp: str | None = None,
    root: str = LANDING_ROOT,
) -> str:
    timestamp = timestamp or get_current_timestamp()
    day = datetime.strptime(timestamp, CREATED_AT_FORMAT).strftime("%Y-%m-%d")
    return f"{root}/{record_type}/dt={day}/{timestamp}-{run_id}-{uuid4().hex[:8]}.parquet"


def build_table(record_type: RecordType, rows: list[dict]) -> pa.Table:
    """Arrow table from the declared schema."""

    return pa.Table.from_pylist(rows, schema=RECORD_TYPE_TO_SCHEMA[record_type])


def validate_rows(rows: dict[RecordType, list[dict]]) -> None:
    for record_type, type_rows in rows.items():
        build_table(record_type, type_rows)


def write_rows(
    record_type: RecordType,
    rows: list[dict],
    run_id: str,
    filesystem: FileSystem | None = None,
    root: str = LANDING_ROOT,
) -> str:
    """Write one record type's rows to a new file. Returns its path."""

    for row in rows:
        row["run_id"] = run_id

    path = build_path(record_type, run_id, root=root)
    table = build_table(record_type, rows)
    pq.write_table(table, path, filesystem=filesystem or build_filesystem(), compression="zstd")
    return path


def write_buffer(
    buffer: RepoBuffer,
    run_id: str,
    filesystem: FileSystem | None = None,
    root: str = LANDING_ROOT,
) -> list[str]:
    """Write every non-empty record type. Raises on the first failure; never clears."""

    filesystem = filesystem or build_filesystem()
    return [
        write_rows(record_type, type_buffer.rows, run_id, filesystem, root)
        for record_type, type_buffer in buffer.buffers.items()
        if type_buffer.rows
    ]
