"""Combined Parquet columns and empty-table helpers for the name-match export."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from experiments.client_request_2026_09_09.constants import PARQUET_FILE_COMPRESSION
from experiments.client_request_2026_09_09.urls import bsky_post_url

COLUMN_URI = "uri"
COLUMN_DID = "did"
COLUMN_TEXT = "text"
COLUMN_CREATED_AT = "created_at"
COLUMN_MATCHED_CANDIDATE = "matched_candidate"
COLUMN_MATCHED_NAME_STRING = "matched_name_string"
COLUMN_URL = "url"

ATHENA_COLUMNS: tuple[str, ...] = (
    COLUMN_URI,
    COLUMN_DID,
    COLUMN_TEXT,
    COLUMN_CREATED_AT,
    COLUMN_MATCHED_CANDIDATE,
    COLUMN_MATCHED_NAME_STRING,
)

COMBINED_COLUMNS: tuple[str, ...] = ATHENA_COLUMNS + (COLUMN_URL,)

ATHENA_SCHEMA: pa.Schema = pa.schema(
    [
        pa.field(COLUMN_URI, pa.string()),
        pa.field(COLUMN_DID, pa.string()),
        pa.field(COLUMN_TEXT, pa.string()),
        pa.field(COLUMN_CREATED_AT, pa.timestamp("us")),
        pa.field(COLUMN_MATCHED_CANDIDATE, pa.string()),
        pa.field(COLUMN_MATCHED_NAME_STRING, pa.string()),
    ]
)

COMBINED_SCHEMA: pa.Schema = ATHENA_SCHEMA.append(pa.field(COLUMN_URL, pa.string()))


@dataclass(frozen=True)
class CandidateMetadataRecord:
    """One candidate object inside ``metadata.json``."""

    candidate_id: str
    display_name: str
    primary_date: str
    query_start: str
    query_end: str
    name_strings: tuple[str, ...]
    row_count: int
    s3_parquet_uri: str


@dataclass(frozen=True)
class RunMetadata:
    """Serialized run document written to ``metadata.json``."""

    run_timestamp: str
    glue_database: str
    glue_table: str
    workgroup: str
    coverage_start: str
    match_rule: str
    is_criticism_filter: bool
    s3_bucket: str
    s3_prefix: str
    candidates: tuple[CandidateMetadataRecord, ...]
    notes: tuple[str, ...]


def empty_export_table() -> pa.Table:
    """Return a zero-row table with the Athena UNLOAD column set."""

    return ATHENA_SCHEMA.empty_table()


def empty_combined_table() -> pa.Table:
    """Return a zero-row table with the combined ``posts.parquet`` schema."""

    return COMBINED_SCHEMA.empty_table()


def with_url_column(table: pa.Table) -> pa.Table:
    """Return ``table`` with a ``url`` column interpolated from each AT-URI.

    Existing ``url`` values are replaced. Malformed AT-URIs become null.

    Parameters
    ----------
    table
        Rows that include a ``uri`` column.

    Returns
    -------
    pa.Table
        The same rows plus ``url``.
    """

    urls = pa.array(
        [bsky_post_url(uri) for uri in table.column(COLUMN_URI).to_pylist()],
        type=pa.string(),
    )
    if COLUMN_URL in table.column_names:
        index = table.schema.get_field_index(COLUMN_URL)
        return table.set_column(index, COLUMN_URL, urls)
    return table.append_column(COLUMN_URL, urls)


def write_export_parquet(path: Path, table: pa.Table) -> None:
    """Write Athena-shaped Parquet without the derived ``url`` column."""

    ordered = table.select(list(ATHENA_COLUMNS))
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(ordered, path, compression=PARQUET_FILE_COMPRESSION)


def write_combined_parquet(path: Path, table: pa.Table) -> None:
    """Write ``table`` as zstd Parquet with combined-column order.

    Parameters
    ----------
    path
        Destination Parquet path. Parent directories are created.
    table
        Rows to write. ``url`` is interpolated from ``uri`` before write.
        Columns are selected into ``COMBINED_COLUMNS`` order.
    """

    ordered = with_url_column(table).select(list(COMBINED_COLUMNS))
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(ordered, path, compression=PARQUET_FILE_COMPRESSION)
