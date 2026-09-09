"""Shared Parquet writers and fake AWS clients for the 2026-09-09 export tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pyarrow as pa
import pyarrow.parquet as pq

from experiments.client_request_2026_09_09.constants import (
    CANDIDATES,
    PARQUET_FILE_COMPRESSION,
    Candidate,
    unload_object_prefix,
)
from experiments.client_request_2026_09_09.schemas import COLUMN_CREATED_AT, COMBINED_SCHEMA

DEFAULT_RUN_TIMESTAMP = "2026_09_09-12:00:00"
UNLOAD_PART_FILENAME = "part-00000.parquet"


class FakeAthena:
    """Records ``run_query`` calls without contacting AWS."""

    def __init__(self) -> None:
        self.queries: list[tuple[str, str, str]] = []

    def run_query(self, query: str, database: str, workgroup: str) -> str:
        self.queries.append((query, database, workgroup))
        return "query-execution-id"


class FakeS3Client:
    """Serves registered objects and records uploads without contacting AWS."""

    def __init__(self) -> None:
        self.objects: dict[str, Path] = {}
        self.uploads: list[tuple[str, str, str]] = []
        self.delete_objects = MagicMock()

    def register_object(self, key: str, path: Path) -> None:
        self.objects[key] = path

    def get_paginator(self, operation_name: str):
        if operation_name != "list_objects_v2":
            raise ValueError(operation_name)
        return _FakeListPaginator(self)

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        source = self.objects[key]
        Path(filename).write_bytes(source.read_bytes())

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        self.uploads.append((filename, bucket, key))


class _FakeListPaginator:
    def __init__(self, s3_client: FakeS3Client) -> None:
        self._s3_client = s3_client

    def paginate(self, Bucket: str, Prefix: str):
        matching = [
            {"Key": key}
            for key in self._s3_client.objects
            if key.startswith(Prefix)
        ]
        if matching:
            yield {"Contents": matching}
            return
        yield {}


def write_combined_rows(path: Path, rows: list[dict]) -> Path:
    """Write ``rows`` as a tiny combined-schema Parquet file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=COMBINED_SCHEMA)
    pq.write_table(table, path, compression=PARQUET_FILE_COMPRESSION)
    return path


def sample_row(
    uri: str,
    matched_candidate: str,
    matched_name_string: str,
    text: str = "hello",
    did: str = "did:plc:test",
) -> dict:
    return {
        "uri": uri,
        "did": did,
        "text": text,
        "created_at": datetime(2026, 8, 15, 12, 0, 0),
        "matched_candidate": matched_candidate,
        "matched_name_string": matched_name_string,
    }


def candidate_by_id(candidate_id: str) -> Candidate:
    return next(candidate for candidate in CANDIDATES if candidate.candidate_id == candidate_id)


def unload_part_key(run_timestamp: str, candidate_id: str) -> str:
    return f"{unload_object_prefix(run_timestamp, candidate_id)}{UNLOAD_PART_FILENAME}"


def assert_combined_timestamp_is_unaware(table: pa.Table) -> None:
    field = table.schema.field(COLUMN_CREATED_AT)
    assert pa.types.is_timestamp(field.type)
    assert field.type.tz is None
