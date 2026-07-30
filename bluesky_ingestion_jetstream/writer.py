"""Write buffered events to disk."""

from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from bluesky_ingestion_jetstream.schemas.arrow_schemas import RECORD_TYPE_TO_SCHEMA
from lib.timestamp_utils import CREATED_AT_FORMAT


def build_path(record_type: str, data_dir: Path) -> Path:
    """Timestamped Parquet path for one flush of one record type.

    The repo's timestamp format is zero-padded, so filenames sort chronologically.
    It only resolves to the second, so a suffix is added rather than silently
    overwriting a file from a flush in the same second.
    """

    directory = data_dir / record_type
    directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime(CREATED_AT_FORMAT)
    path = directory / f"{timestamp}.parquet"
    seq = 1
    while path.exists():
        path = directory / f"{timestamp}-{seq}.parquet"
        seq += 1
    return path


def write(record_type: str, rows: list[dict], data_dir: Path, run_id: str) -> Path:
    """Write rows to a file under `data_dir` and return the path.

    `run_id` is stamped here rather than in the parsers, because it is fixed for
    the life of the process and threading it through every parser signature would
    be churn for a column that cannot vary per row. The rows are mutated in place:
    a flush batch can hold millions of dicts, and copying all of them to add one
    key is a real cost for no benefit -- the buffer clears immediately after.
    """

    for row in rows:
        row["run_id"] = run_id

    table = pa.Table.from_pylist(rows, schema=RECORD_TYPE_TO_SCHEMA[record_type])
    path = build_path(record_type, data_dir)
    pq.write_table(table, path, compression="snappy")
    return path
