"""Tests for the commit path: retries, the idempotency guard, and dead-lettering.

Every test runs against a fake table. Nothing here touches AWS, and the backoff
sleeps are patched out, so the suite stays sub-second despite exercising a retry
policy measured in seconds.
"""

import logging

import pyarrow as pa
import pytest
from pyiceberg.exceptions import CommitFailedException, NoSuchTableError

from bluesky_ingestion_jetstream.aws.constants import COMMIT_MAX_ATTEMPTS, SNAPSHOT_FLUSH_ID_TAG
from bluesky_ingestion_jetstream.constants import RECORD_TYPES
from bluesky_ingestion_jetstream.schemas.arrow_schemas import RECORD_TYPE_TO_SCHEMA
from bluesky_ingestion_jetstream.sinks.iceberg import IcebergSink
from tests.bluesky_ingestion_jetstream.conftest import RUN_ID


class FakeSnapshot:
    def __init__(self, summary: dict):
        self.summary = summary


class FakeTable:
    """A table that records appends and can be told to fail the first N of them.

    `committed_despite_failing` models the case a retry cannot otherwise see: the
    Glue update landed but the response was lost, so the caller observes an error
    for a commit that actually succeeded.
    """

    def __init__(self, record_type: str, fail_times: int = 0, error: Exception | None = None):
        self._schema = RECORD_TYPE_TO_SCHEMA[record_type]
        self.appends: list[pa.Table] = []
        self.flush_ids: list[str] = []
        self.fail_times = fail_times
        self.error = error or CommitFailedException("glue said no")
        self.committed_despite_failing = False
        self.refreshes = 0
        self._snapshots: list[FakeSnapshot] = []

    def schema(self):
        class Schema:
            def __init__(self, arrow):
                self._arrow = arrow

            def as_arrow(self):
                return self._arrow

        return Schema(self._schema)

    def append(self, arrow: pa.Table, snapshot_properties: dict | None = None) -> None:
        flush_id = (snapshot_properties or {}).get(SNAPSHOT_FLUSH_ID_TAG, "")
        if self.fail_times > 0:
            self.fail_times -= 1
            if self.committed_despite_failing:
                self._snapshots.append(FakeSnapshot({SNAPSHOT_FLUSH_ID_TAG: flush_id}))
            raise self.error
        self.appends.append(arrow)
        self.flush_ids.append(flush_id)
        self._snapshots.append(FakeSnapshot({SNAPSHOT_FLUSH_ID_TAG: flush_id}))

    def refresh(self) -> None:
        self.refreshes += 1

    def snapshots(self):
        return self._snapshots


@pytest.fixture(autouse=True)
def no_sleeping(monkeypatch):
    """Run the real backoff schedule without waiting for it."""

    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _seconds: None)


class RecordingDeadLetter:
    """Stands in for the S3 write, recording what was given up on."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict], str]] = []

    def __call__(self, record_type: str, rows: list[dict], run_id: str, **kwargs) -> str:
        self.calls.append((record_type, list(rows), run_id))
        return "s3://dead-letter/file.parquet"


@pytest.fixture
def recorded_dead_letters() -> RecordingDeadLetter:
    return RecordingDeadLetter()


def build_sink(tables: dict, dead_letter) -> IcebergSink:
    return IcebergSink(tables, RUN_ID, dead_letter=dead_letter)


class TestSuccessfulCommit:
    @pytest.mark.parametrize("record_type", RECORD_TYPES)
    def test_rows_reach_the_table(self, record_type, rows_factory, recorded_dead_letters):
        table = FakeTable(record_type)
        rows = rows_factory(record_type, 3)

        build_sink({record_type: table}, recorded_dead_letters).write(record_type, rows)

        assert len(table.appends) == 1
        assert table.appends[0].num_rows == 3
        assert recorded_dead_letters.calls == []

    def test_every_row_is_stamped_with_the_run_id(self, rows_factory, recorded_dead_letters):
        table = FakeTable("likes")

        build_sink({"likes": table}, recorded_dead_letters).write("likes", rows_factory("likes", 2))

        assert table.appends[0].column("run_id").to_pylist() == [RUN_ID, RUN_ID]

    def test_arrow_is_built_from_the_tables_schema(self, rows_factory, recorded_dead_letters):
        """Using the declared schema would write ids the table does not know.

        Iceberg matches columns by field id, so the mismatch does not raise -- the
        affected columns simply read back as NULL.
        """

        table = FakeTable("posts")

        build_sink({"posts": table}, recorded_dead_letters).write("posts", rows_factory("posts", 1))

        assert table.appends[0].schema.equals(table.schema().as_arrow())

    def test_the_commit_is_tagged_with_a_flush_id(self, rows_factory, recorded_dead_letters):
        table = FakeTable("posts")

        build_sink({"posts": table}, recorded_dead_letters).write("posts", rows_factory("posts", 1))

        assert table.flush_ids[0]

    def test_each_flush_gets_its_own_id(self, rows_factory, recorded_dead_letters):
        table = FakeTable("posts")
        sink = build_sink({"posts": table}, recorded_dead_letters)

        sink.write("posts", rows_factory("posts", 1))
        sink.write("posts", rows_factory("posts", 1))

        assert table.flush_ids[0] != table.flush_ids[1]

    def test_an_empty_batch_is_not_committed(self, recorded_dead_letters):
        """An empty append would burn a full commit -- and a snapshot -- on nothing."""

        table = FakeTable("posts")

        build_sink({"posts": table}, recorded_dead_letters).write("posts", [])

        assert table.appends == []


class TestRetry:
    def test_a_transient_failure_is_retried_and_can_succeed(
        self, rows_factory, recorded_dead_letters
    ):
        table = FakeTable("posts", fail_times=2)

        build_sink({"posts": table}, recorded_dead_letters).write("posts", rows_factory("posts", 2))

        assert len(table.appends) == 1
        assert recorded_dead_letters.calls == []

    def test_it_gives_up_after_the_configured_attempts(self, rows_factory, recorded_dead_letters):
        """Three attempts, because the read loop is stalled for every one of them."""

        table = FakeTable("posts", fail_times=99)
        rows = rows_factory("posts", 2)

        build_sink({"posts": table}, recorded_dead_letters).write("posts", rows)

        assert len(recorded_dead_letters.calls) == 1
        record_type, dead_rows, run_id = recorded_dead_letters.calls[0]
        assert (record_type, len(dead_rows), run_id) == ("posts", 2, RUN_ID)

    def test_a_code_bug_is_not_retried(self, rows_factory, recorded_dead_letters):
        """A schema mismatch fails identically three times; retrying only delays it."""

        table = FakeTable("posts", fail_times=99, error=ValueError("schema mismatch"))

        build_sink({"posts": table}, recorded_dead_letters).write("posts", rows_factory("posts", 1))

        assert table.refreshes == 0
        assert len(recorded_dead_letters.calls) == 1

    def test_a_missing_table_is_not_retried(self, rows_factory, recorded_dead_letters):
        table = FakeTable("posts", fail_times=99, error=NoSuchTableError("gone"))

        build_sink({"posts": table}, recorded_dead_letters).write("posts", rows_factory("posts", 1))

        assert table.refreshes == 0

    def test_a_lost_response_does_not_duplicate_the_rows(
        self, rows_factory, recorded_dead_letters, caplog
    ):
        """The commit landed but the caller saw an error. Iceberg would not dedupe it."""

        table = FakeTable("posts", fail_times=1)
        table.committed_despite_failing = True

        with caplog.at_level(logging.WARNING):
            build_sink({"posts": table}, recorded_dead_letters).write(
                "posts", rows_factory("posts", 2)
            )

        assert table.appends == []
        assert table.refreshes == 1
        assert recorded_dead_letters.calls == []
        assert "already landed" in caplog.text

    def test_the_first_attempt_does_not_pay_for_the_check(
        self, rows_factory, recorded_dead_letters
    ):
        """`already_committed` is a Glue GetTable; nothing can have landed yet."""

        table = FakeTable("posts")

        build_sink({"posts": table}, recorded_dead_letters).write("posts", rows_factory("posts", 1))

        assert table.refreshes == 0

    def test_attempts_are_bounded_by_the_constant(self, rows_factory, recorded_dead_letters):
        table = FakeTable("posts", fail_times=99)
        start = table.fail_times

        build_sink({"posts": table}, recorded_dead_letters).write("posts", rows_factory("posts", 1))

        assert start - table.fail_times == COMMIT_MAX_ATTEMPTS


class TestPerRecordTypeIsolation:
    def test_one_failing_table_does_not_block_the_others(self, rows_factory, recorded_dead_letters):
        """Four separate commits, so a throttled table cannot cost the other three."""

        tables = {record_type: FakeTable(record_type) for record_type in RECORD_TYPES}
        tables["likes"] = FakeTable("likes", fail_times=99)
        sink = build_sink(tables, recorded_dead_letters)

        for record_type in RECORD_TYPES:
            sink.write(record_type, rows_factory(record_type, 1))

        assert [rt for rt, _, _ in recorded_dead_letters.calls] == ["likes"]
        for record_type in ("posts", "reposts", "follows"):
            assert len(tables[record_type].appends) == 1

    def test_a_dead_letter_failure_propagates(self, rows_factory):
        """Nothing durable is left, so the caller must not be told this was handled."""

        def exploding_dead_letter(*args, **kwargs):
            raise RuntimeError("s3 unreachable")

        table = FakeTable("posts", fail_times=99)

        with pytest.raises(RuntimeError, match="s3 unreachable"):
            build_sink({"posts": table}, exploding_dead_letter).write(
                "posts", rows_factory("posts", 1)
            )
