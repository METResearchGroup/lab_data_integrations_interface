"""Tests for the buffers, the flush triggers, and the flush itself."""

import json

import pytest

from bluesky_ingestion_jetstream.constants import (
    FLUSH_REASON_AGE,
    FLUSH_REASON_SIZE,
    RECORD_TYPES,
)
from bluesky_ingestion_jetstream.storage import buffer as buffer_module
from bluesky_ingestion_jetstream.storage.buffer import (
    Buffer,
    BufferSet,
    flush,
    get_flush_summary,
    row_bytes,
)


class RecordingSink:
    """A sink that remembers what it was handed, and can be told to fail."""

    def __init__(self, error: Exception | None = None):
        self.calls: list[tuple[str, list[dict]]] = []
        self.error = error

    def write(self, record_type: str, rows: list[dict]) -> None:
        if self.error is not None:
            raise self.error
        self.calls.append((record_type, list(rows)))


@pytest.fixture
def sink():
    """The flush tests need a destination, not a filesystem."""

    return RecordingSink()


@pytest.fixture
def filled(rows_factory):
    """A BufferSet holding a different row count per record type."""

    buffer_set = BufferSet()
    for count, record_type in enumerate(RECORD_TYPES, start=1):
        for row in rows_factory(record_type, count):
            buffer_set.add(record_type, row)
    return buffer_set


class TestRowBytes:
    def test_matches_the_serialized_length(self):
        row = {"uri": "at://did:plc:x/app.bsky.feed.like/abc", "cid": None}

        assert row_bytes(row) == len(json.dumps(row, default=str).encode())

    def test_handles_datetime_columns(self, rows_factory):
        """`default=str` is what keeps the created_at column serializable."""

        assert row_bytes(rows_factory("likes", 1)[0]) > 0

    def test_counts_bytes_not_characters(self):
        assert row_bytes({"text": "αααα"}) > row_bytes({"text": "aaaa"})


class TestBuffer:
    def test_starts_empty(self):
        buffer = Buffer()

        assert buffer.rows == []
        assert buffer.size == 0

    def test_add_appends_the_row(self, rows_factory):
        buffer = Buffer()
        row = rows_factory("likes", 1)[0]
        buffer.add(row)

        assert buffer.rows == [row]

    def test_size_grows_by_the_serialized_length(self, rows_factory):
        buffer = Buffer()
        expected = 0
        for row in rows_factory("likes", 3):
            buffer.add(row)
            expected += row_bytes(row)

            assert buffer.size == expected

    def test_clear_resets_rows_and_size(self, rows_factory):
        buffer = Buffer()
        buffer.add(rows_factory("likes", 1)[0])
        buffer.clear()

        assert buffer.rows == []
        assert buffer.size == 0

    def test_clear_rebinds_rather_than_mutating(self, rows_factory):
        """`flush` hands the writer `buffer.rows` and clears afterward. Rebinding
        is what leaves that reference intact instead of emptying it."""

        buffer = Buffer()
        buffer.add(rows_factory("likes", 1)[0])
        held = buffer.rows
        buffer.clear()

        assert len(held) == 1

    def test_refills_after_clearing(self, rows_factory):
        buffer = Buffer()
        buffer.add(rows_factory("likes", 1)[0])
        buffer.clear()
        row = rows_factory("likes", 1)[0]
        buffer.add(row)

        assert buffer.size == row_bytes(row)

    def test_buffers_do_not_share_row_lists(self):
        """A mutable default would make every Buffer share one list."""

        first, second = Buffer(), Buffer()
        first.add({"uri": "at://did:plc:x/app.bsky.feed.like/abc"})

        assert second.rows == []

    def test_ignores_a_repeated_uri(self, rows_factory):
        """A reconnect redelivers events already buffered."""

        buffer = Buffer()
        row = rows_factory("likes", 1)[0]
        buffer.add(row)
        buffer.add(dict(row))

        assert buffer.rows == [row]
        assert buffer.size == row_bytes(row)

    def test_keeps_rows_with_distinct_uris(self, rows_factory):
        buffer = Buffer()
        for row in rows_factory("likes", 3):
            buffer.add(row)

        assert len(buffer.rows) == 3

    def test_deduplicates_only_within_a_flush_window(self, rows_factory):
        """`clear` drops `seen`, so a URI already written can be buffered again."""

        buffer = Buffer()
        row = rows_factory("likes", 1)[0]
        buffer.add(row)
        buffer.clear()
        buffer.add(row)

        assert buffer.rows == [row]

    def test_buffers_do_not_share_seen_uris(self, rows_factory):
        """A mutable default would let one buffer suppress another's rows."""

        first, second = Buffer(), Buffer()
        row = rows_factory("likes", 1)[0]
        first.add(row)
        second.add(row)

        assert second.rows == [row]


class TestBufferSet:
    def test_owns_one_buffer_per_record_type(self):
        assert set(BufferSet().buffers) == set(RECORD_TYPES)

    def test_size_sums_every_buffer(self, rows_factory):
        buffer_set = BufferSet()
        expected = 0
        for record_type in RECORD_TYPES:
            row = rows_factory(record_type, 1)[0]
            buffer_set.add(record_type, row)
            expected += row_bytes(row)

        assert buffer_set.size == expected

    def test_size_is_zero_when_empty(self):
        assert BufferSet().size == 0

    def test_size_cannot_drift_from_its_children(self, rows_factory):
        """Derived rather than counted, so clearing one buffer stays consistent."""

        buffer_set = BufferSet()
        for record_type in RECORD_TYPES:
            buffer_set.add(record_type, rows_factory(record_type, 1)[0])
        buffer_set.buffers["likes"].clear()

        assert buffer_set.size == sum(b.size for b in buffer_set.buffers.values())

    def test_add_routes_to_the_matching_buffer(self, rows_factory):
        buffer_set = BufferSet()
        buffer_set.add("follows", rows_factory("follows", 1)[0])

        assert len(buffer_set.buffers["follows"].rows) == 1
        assert buffer_set.buffers["likes"].rows == []

    def test_add_ignores_a_repeated_uri(self, rows_factory):
        row = rows_factory("follows", 1)[0]
        buffer_set = BufferSet()
        buffer_set.add("follows", row)
        buffer_set.add("follows", dict(row))

        assert buffer_set.buffers["follows"].rows == [row]
        assert buffer_set.size == row_bytes(row)

    def test_add_rejects_an_unknown_record_type(self):
        """Signals the collection map and the buffers have drifted apart."""

        with pytest.raises(KeyError):
            BufferSet().add("blocks", {"uri": "at://x/y/z"})


class TestShouldFlush:
    def test_false_when_empty(self):
        assert BufferSet(max_size_bytes=1, max_age_seconds=0.0).should_flush() is False

    def test_empty_set_never_flushes_on_age(self, monkeypatch):
        """The size guard is what stops the timer writing empty files forever."""

        monkeypatch.setattr(buffer_module.time, "monotonic", lambda: 1e9)

        assert BufferSet(max_age_seconds=1.0).should_flush() is False

    def test_false_below_both_thresholds(self, rows_factory):
        buffer_set = BufferSet(max_size_bytes=10**9, max_age_seconds=10**9)
        buffer_set.add("likes", rows_factory("likes", 1)[0])

        assert buffer_set.should_flush() is False

    def test_true_at_the_size_threshold(self, rows_factory):
        row = rows_factory("likes", 1)[0]
        buffer_set = BufferSet(max_size_bytes=row_bytes(row), max_age_seconds=10**9)
        buffer_set.add("likes", row)

        assert buffer_set.size == buffer_set.max_size_bytes
        assert buffer_set.should_flush() is True

    def test_size_threshold_counts_across_buffers(self, rows_factory):
        """One buffer alone is under the threshold; together they trip it."""

        rows = [rows_factory(rt, 1)[0] for rt in ("likes", "posts")]
        total = sum(row_bytes(row) for row in rows)
        buffer_set = BufferSet(max_size_bytes=total, max_age_seconds=10**9)

        buffer_set.add("likes", rows[0])
        assert buffer_set.should_flush() is False

        buffer_set.add("posts", rows[1])
        assert buffer_set.should_flush() is True

    def test_true_at_the_age_threshold(self, rows_factory, monkeypatch):
        clock = [100.0]
        monkeypatch.setattr(buffer_module.time, "monotonic", lambda: clock[0])
        buffer_set = BufferSet(max_size_bytes=10**9, max_age_seconds=30.0)
        buffer_set.add("reposts", rows_factory("reposts", 1)[0])

        clock[0] = 129.9
        assert buffer_set.should_flush() is False

        clock[0] = 130.0
        assert buffer_set.should_flush() is True

    def test_age_is_measured_from_the_last_flush(self, rows_factory, monkeypatch):
        """Not from when a row arrived -- rows are not individually timestamped."""

        clock = [100.0]
        monkeypatch.setattr(buffer_module.time, "monotonic", lambda: clock[0])
        buffer_set = BufferSet(max_size_bytes=10**9, max_age_seconds=30.0)

        clock[0] = 135.0
        buffer_set.add("posts", rows_factory("posts", 1)[0])

        assert buffer_set.should_flush() is True


class TestFlushReason:
    def test_raises_when_no_threshold_is_hit(self):
        """Naming a threshold that never tripped would put a lie on the dashboard."""

        with pytest.raises(ValueError, match="no flush threshold"):
            BufferSet().flush_reason()

    def test_size_when_the_size_threshold_trips(self, rows_factory):
        row = rows_factory("likes", 1)[0]
        buffer_set = BufferSet(max_size_bytes=row_bytes(row), max_age_seconds=10**9)
        buffer_set.add("likes", row)

        assert buffer_set.flush_reason() == FLUSH_REASON_SIZE

    def test_age_when_only_the_timer_trips(self, rows_factory, monkeypatch):
        clock = [100.0]
        monkeypatch.setattr(buffer_module.time, "monotonic", lambda: clock[0])
        buffer_set = BufferSet(max_size_bytes=10**9, max_age_seconds=30.0)
        buffer_set.add("posts", rows_factory("posts", 1)[0])

        clock[0] = 130.0
        assert buffer_set.flush_reason() == FLUSH_REASON_AGE

    def test_size_wins_when_both_trip(self, rows_factory, monkeypatch):
        clock = [100.0]
        monkeypatch.setattr(buffer_module.time, "monotonic", lambda: clock[0])
        row = rows_factory("likes", 1)[0]
        buffer_set = BufferSet(max_size_bytes=row_bytes(row), max_age_seconds=30.0)
        buffer_set.add("likes", row)

        clock[0] = 130.0
        assert buffer_set.flush_reason() == FLUSH_REASON_SIZE


class TestGetFlushSummary:
    def test_counts_rows_and_bytes_per_record_type(self, filled):
        summary = get_flush_summary(filled, FLUSH_REASON_AGE)

        assert summary.reason == FLUSH_REASON_AGE
        assert summary.rows == dict(zip(RECORD_TYPES, [1, 2, 3, 4]))
        assert summary.sizes == {rt: filled.buffers[rt].size for rt in RECORD_TYPES}

    def test_omits_empty_buffers(self, rows_factory):
        buffer_set = BufferSet()
        buffer_set.add("posts", rows_factory("posts", 1)[0])

        summary = get_flush_summary(buffer_set, FLUSH_REASON_SIZE)

        assert summary.rows == {"posts": 1}
        assert set(summary.sizes) == {"posts"}

    def test_reads_zero_once_the_buffers_are_flushed(self, filled, sink):
        """Taken after a flush it reports nothing, which is why order matters."""

        flush(filled, sink)

        assert get_flush_summary(filled, FLUSH_REASON_AGE).rows == {}


class TestMarkFlushed:
    def test_restarts_the_age_timer(self, rows_factory, monkeypatch):
        clock = [100.0]
        monkeypatch.setattr(buffer_module.time, "monotonic", lambda: clock[0])
        buffer_set = BufferSet(max_size_bytes=10**9, max_age_seconds=30.0)
        buffer_set.add("posts", rows_factory("posts", 1)[0])

        clock[0] = 140.0
        assert buffer_set.should_flush() is True

        buffer_set.mark_flushed()
        assert buffer_set.should_flush() is False


class TestFlush:
    def test_writes_every_non_empty_buffer(self, filled, sink):
        flush(filled, sink)

        assert {rt: len(rows) for rt, rows in sink.calls} == dict(zip(RECORD_TYPES, [1, 2, 3, 4]))

    def test_empty_buffers_write_nothing(self, rows_factory, sink):
        buffer_set = BufferSet()
        buffer_set.add("posts", rows_factory("posts", 1)[0])

        flush(buffer_set, sink)

        assert [record_type for record_type, _ in sink.calls] == ["posts"]

    def test_nothing_buffered_writes_nothing(self, sink):
        flush(BufferSet(), sink)

        assert sink.calls == []

    def test_buffers_are_empty_afterward(self, filled, sink):
        flush(filled, sink)

        assert filled.size == 0
        for buffer in filled.buffers.values():
            assert buffer.rows == []

    def test_restarts_the_age_timer(self, filled, sink, monkeypatch):
        clock = [500.0]
        monkeypatch.setattr(buffer_module.time, "monotonic", lambda: clock[0])

        flush(filled, sink)

        assert filled.last_flush == 500.0

    def test_timer_restarts_with_nothing_to_write(self, sink, monkeypatch):
        """A size-triggered flush must not leave a stale timer that fires next tick."""

        clock = [500.0]
        monkeypatch.setattr(buffer_module.time, "monotonic", lambda: clock[0])
        buffer_set = BufferSet()

        flush(buffer_set, sink)

        assert buffer_set.last_flush == 500.0

    def test_rows_survive_a_write_failure(self, filled):
        """Clearing before the write returns would lose the batch.

        A sink that dead-letters has handled the batch and returns normally, so
        this is the case where even that failed and the rows are still ours.
        """

        failing = RecordingSink(error=OSError("s3 unreachable"))
        expected = {rt: len(b.rows) for rt, b in filled.buffers.items()}

        with pytest.raises(OSError, match="s3 unreachable"):
            flush(filled, failing)

        assert {rt: len(b.rows) for rt, b in filled.buffers.items()} == expected

    def test_the_sink_never_sees_a_duplicated_uri(self, rows_factory, sink):
        rows = rows_factory("likes", 2)
        buffer_set = BufferSet()
        for row in (*rows, dict(rows[0])):
            buffer_set.add("likes", row)

        flush(buffer_set, sink)

        assert sink.calls == [("likes", rows)]

    def test_the_sink_receives_the_rows_it_should(self, rows_factory, sink):
        rows = rows_factory("follows", 2)
        buffer_set = BufferSet()
        for row in rows:
            buffer_set.add("follows", row)

        flush(buffer_set, sink)

        assert sink.calls == [("follows", rows)]
