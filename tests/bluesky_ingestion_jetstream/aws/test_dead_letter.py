"""Tests for the dead letter: where batches go when Iceberg will not take them."""

import logging
import re
from datetime import UTC, datetime

import pyarrow.parquet as pq
import pytest
from pyarrow.fs import LocalFileSystem

from bluesky_ingestion_jetstream.aws import dead_letter as dead_letter_module
from bluesky_ingestion_jetstream.aws.constants import DEAD_LETTER_ROOT, S3_BUCKET, S3_PREFIX
from bluesky_ingestion_jetstream.aws.dead_letter import (
    DeadLetterError,
    build_path,
    build_table,
    write_dead_letter,
)
from bluesky_ingestion_jetstream.constants import RECORD_TYPES
from bluesky_ingestion_jetstream.schemas.arrow_schemas import RECORD_TYPE_TO_SCHEMA
from tests.bluesky_ingestion_jetstream.conftest import RUN_ID

MOMENT = datetime(2026, 7, 23, 6, 48, 11, tzinfo=UTC)


@pytest.fixture
def local_root(tmp_path):
    """A local stand-in for the S3 prefix, with the day directory pre-created.

    `pq.write_table` will not create parent directories, and S3 has none to
    create, so the test supplies them rather than the code doing it needlessly.
    """

    day = datetime.now(UTC).strftime("%Y-%m-%d")
    for record_type in RECORD_TYPES:
        (tmp_path / record_type / f"dt={day}").mkdir(parents=True)
    return str(tmp_path)


class TestBuildPath:
    def test_stays_out_of_the_warehouse(self):
        """Files under a table's location are exactly what orphan cleanup deletes."""

        assert not build_path("posts", RUN_ID).startswith(f"{S3_BUCKET}/{S3_PREFIX}/")
        assert DEAD_LETTER_ROOT.startswith(f"{S3_BUCKET}/dead_letter/")

    def test_partitions_by_record_type_then_day(self):
        path = build_path("likes", RUN_ID, now=MOMENT, root="root")

        assert path.startswith("root/likes/dt=2026-07-23/")

    def test_names_carry_the_timestamp_and_run_id(self):
        path = build_path("likes", RUN_ID, now=MOMENT, root="root")

        assert path.split("/")[-1].startswith(f"2026_07_23-06:48:11-{RUN_ID}-")
        assert path.endswith(".parquet")

    def test_two_batches_in_one_second_do_not_collide(self):
        """S3 has no create-if-absent; a collision would overwrite unrecovered data."""

        first = build_path("likes", RUN_ID, now=MOMENT, root="root")
        second = build_path("likes", RUN_ID, now=MOMENT, root="root")

        assert first != second

    def test_names_sort_chronologically(self):
        """The repo timestamp format is zero-padded, so lexical order is time order."""

        earlier = build_path("posts", RUN_ID, now=MOMENT, root="root")
        later = build_path(
            "posts", RUN_ID, now=datetime(2026, 7, 23, 11, 4, 9, tzinfo=UTC), root="root"
        )

        assert sorted([later, earlier]) == [earlier, later]


class TestBuildTable:
    @pytest.mark.parametrize("record_type", RECORD_TYPES)
    def test_uses_the_declared_schema_not_the_catalogs(self, record_type, rows_factory):
        """The catalog may be exactly what is broken, so it must not be consulted."""

        table = build_table(record_type, rows_factory(record_type, 3))

        assert table.schema.equals(RECORD_TYPE_TO_SCHEMA[record_type])
        assert table.num_rows == 3


class TestWriteDeadLetter:
    @pytest.mark.parametrize("record_type", RECORD_TYPES)
    def test_rows_survive_the_round_trip(self, record_type, rows_factory, local_root):
        """Rows arrive already stamped, because the sink stamps before it commits."""

        rows = [row | {"run_id": RUN_ID} for row in rows_factory(record_type, 4)]

        path = write_dead_letter(
            record_type, rows, RUN_ID, filesystem=LocalFileSystem(), root=local_root
        )

        table = pq.read_table(path)
        assert table.select(RECORD_TYPE_TO_SCHEMA[record_type].names).to_pylist() == rows

    def test_the_day_is_readable_as_a_partition_column(self, rows_factory, local_root):
        """`dt=` is Hive-style so a reader recovers the day without opening the file."""

        path = write_dead_letter(
            "posts", rows_factory("posts", 2), RUN_ID, filesystem=LocalFileSystem(), root=local_root
        )

        assert "dt" in pq.read_table(path).column_names

    def test_returns_where_it_wrote(self, rows_factory, local_root):
        path = write_dead_letter(
            "posts", rows_factory("posts", 1), RUN_ID, filesystem=LocalFileSystem(), root=local_root
        )

        assert path.startswith(local_root)
        assert re.search(rf"/posts/dt=\d{{4}}-\d{{2}}-\d{{2}}/.*{RUN_ID}.*\.parquet$", path)

    def test_a_transient_failure_is_retried_once(self, rows_factory, local_root, monkeypatch):
        calls = []
        real = dead_letter_module.pq.write_table

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise OSError("connection reset")
            return real(*args, **kwargs)

        monkeypatch.setattr(dead_letter_module.pq, "write_table", flaky)

        write_dead_letter(
            "likes", rows_factory("likes", 2), RUN_ID, filesystem=LocalFileSystem(), root=local_root
        )

        assert len(calls) == 2

    def test_two_failures_raise_rather_than_retrying_forever(
        self, rows_factory, local_root, monkeypatch
    ):
        """Holding rows until S3 recovers trades one lost batch for the whole buffer."""

        calls = []

        def always_fails(*args, **kwargs):
            calls.append(1)
            raise OSError("s3 unreachable")

        monkeypatch.setattr(dead_letter_module.pq, "write_table", always_fails)

        with pytest.raises(DeadLetterError, match="failed twice"):
            write_dead_letter(
                "posts",
                rows_factory("posts", 3),
                RUN_ID,
                filesystem=LocalFileSystem(),
                root=local_root,
            )

        assert len(calls) == 2

    def test_a_successful_write_is_logged_loudly(self, rows_factory, local_root, caplog):
        """With no replay tool yet, the log line is the only signal rows went missing."""

        with caplog.at_level(logging.ERROR):
            write_dead_letter(
                "follows",
                rows_factory("follows", 2),
                RUN_ID,
                filesystem=LocalFileSystem(),
                root=local_root,
            )

        assert "DEAD LETTER" in caplog.text
        assert "2 follows rows" in caplog.text


class TestCounters:
    """These branches only run once a commit has already failed, so the wiring
    cannot be checked by watching a healthy process."""

    @pytest.fixture
    def counted(self, monkeypatch):
        recorded: dict[str, list] = {"dead_letter": [], "dropped": []}
        monkeypatch.setattr(
            dead_letter_module,
            "record_dead_letter",
            lambda rt, rows: recorded["dead_letter"].append((rt, rows)),
        )
        monkeypatch.setattr(
            dead_letter_module,
            "record_dropped",
            lambda rt, rows: recorded["dropped"].append((rt, rows)),
        )
        return recorded

    def test_counts_rows_that_landed_in_the_dead_letter(self, counted, rows_factory, local_root):
        write_dead_letter(
            "likes", rows_factory("likes", 2), RUN_ID, filesystem=LocalFileSystem(), root=local_root
        )

        assert counted["dead_letter"] == [("likes", 2)]
        assert counted["dropped"] == []

    def test_counts_rows_nothing_durable_accepted(
        self, counted, rows_factory, local_root, monkeypatch
    ):
        """The one metric that means data is gone, not merely misplaced."""

        def always_fails(*args, **kwargs):
            raise OSError("s3 unreachable")

        monkeypatch.setattr(dead_letter_module.pq, "write_table", always_fails)

        with pytest.raises(DeadLetterError):
            write_dead_letter(
                "posts",
                rows_factory("posts", 3),
                RUN_ID,
                filesystem=LocalFileSystem(),
                root=local_root,
            )

        assert counted["dropped"] == [("posts", 3)]
        assert counted["dead_letter"] == []
