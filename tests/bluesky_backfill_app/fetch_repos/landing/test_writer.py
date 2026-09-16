import time
from datetime import UTC, datetime

import pyarrow.parquet as pq
import pytest
from pyarrow.fs import LocalFileSystem

from bluesky_backfill_app.aws.queue import Message
from bluesky_backfill_app.fetch_repos.constants import LANDING_ROOT
from bluesky_backfill_app.fetch_repos.landing.writer import (
    build_path,
    build_table,
    write_buffer,
    write_rows,
)
from bluesky_backfill_app.fetch_repos.storage.buffer import RepoBuffer
from bluesky_ingestion_jetstream.aws.constants import S3_BUCKET, S3_PREFIX
from bluesky_ingestion_jetstream.constants import LIKES, POSTS, RECORD_TYPES
from bluesky_ingestion_jetstream.schemas.arrow_schemas import RECORD_TYPE_TO_SCHEMA

RUN_ID = "run-1"
TIMESTAMP = "2026_07_23-06:48:11"


@pytest.fixture
def local_root(tmp_path):
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    for record_type in RECORD_TYPES:
        (tmp_path / record_type / f"dt={day}").mkdir(parents=True)
    return str(tmp_path)


def row(uri):
    return {"uri": uri, "did": "did:plc:a"}


def message():
    return Message(did="did:plc:a", run_id=None, handle="h", receive_count=1)


def test_path_stays_out_of_the_warehouse():
    assert build_path(POSTS, RUN_ID).startswith(f"{LANDING_ROOT}/")
    assert not LANDING_ROOT.startswith(f"{S3_BUCKET}/{S3_PREFIX}")


def test_path_partitions_by_record_type_then_day():
    path = build_path(LIKES, RUN_ID, timestamp=TIMESTAMP, root="root")

    assert path.startswith("root/likes/dt=2026-07-23/")


def test_filename_carries_the_timestamp_and_run_id():
    path = build_path(LIKES, RUN_ID, timestamp=TIMESTAMP, root="root")

    assert path.split("/")[-1].startswith(f"{TIMESTAMP}-{RUN_ID}-")
    assert path.endswith(".parquet")


def test_two_paths_in_one_second_differ():
    first = build_path(POSTS, RUN_ID, timestamp=TIMESTAMP)
    second = build_path(POSTS, RUN_ID, timestamp=TIMESTAMP)

    assert first != second


@pytest.mark.parametrize("record_type", RECORD_TYPES)
def test_build_table_uses_the_declared_schema(record_type):
    table = build_table(record_type, [row("a"), row("b")])

    assert table.schema.equals(RECORD_TYPE_TO_SCHEMA[record_type])
    assert table.num_rows == 2


def test_write_rows_round_trips_with_the_schema(local_root):
    path = write_rows(POSTS, [row("p1"), row("p2")], RUN_ID, LocalFileSystem(), local_root)

    table = pq.ParquetFile(path).read()
    assert table.schema.equals(RECORD_TYPE_TO_SCHEMA[POSTS])
    assert table.num_rows == 2
    assert table.column("run_id").to_pylist() == [RUN_ID, RUN_ID]


def test_write_buffer_writes_one_file_per_non_empty_type(local_root):
    buffer = RepoBuffer()
    buffer.add(message(), {POSTS: [row("p1")], LIKES: [row("l1"), row("l2")]}, time.monotonic())

    paths = write_buffer(buffer, RUN_ID, LocalFileSystem(), local_root)

    assert sorted(path.split("/")[-3] for path in paths) == [LIKES, POSTS]
    assert sum(pq.read_table(path).num_rows for path in paths) == 3


def test_write_buffer_of_an_empty_buffer_writes_nothing(local_root):
    assert write_buffer(RepoBuffer(), RUN_ID, LocalFileSystem(), local_root) == []


def test_write_buffer_does_not_clear(local_root):
    buffer = RepoBuffer()
    buffer.add(message(), {POSTS: [row("p1")]}, time.monotonic())

    write_buffer(buffer, RUN_ID, LocalFileSystem(), local_root)

    assert len(buffer.buffers[POSTS].rows) == 1
    assert len(buffer.messages) == 1


def test_write_buffer_raises_when_the_write_fails(tmp_path):
    buffer = RepoBuffer()
    buffer.add(message(), {POSTS: [row("p1")]}, time.monotonic())

    with pytest.raises(OSError):
        write_buffer(buffer, RUN_ID, LocalFileSystem(), str(tmp_path / "missing"))
