"""Tests for the buffers, the flush triggers, and the flush itself."""

import json

import pytest

from bluesky_ingestion_jetstream.constants import RECORD_TYPES
from bluesky_ingestion_jetstream.storage import buffer as buffer_module
from bluesky_ingestion_jetstream.storage.buffer import Buffer, BufferSet, flush, row_bytes


@pytest.fixture
def recorded_writes(monkeypatch, tmp_path):
    """Replace the writer so flush tests never touch Parquet."""

    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        buffer_module, "write", lambda rt, rows, data_dir: calls.append((rt, len(rows)))
    )
    return calls


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

    def test_drain_returns_the_rows(self, rows_factory):
        buffer = Buffer()
        rows = rows_factory("likes", 3)
        for row in rows:
            buffer.add(row)

        assert buffer.drain() == rows

    def test_drain_resets_rows_and_size(self, rows_factory):
        buffer = Buffer()
        buffer.add(rows_factory("likes", 1)[0])
        buffer.drain()

        assert buffer.rows == []
        assert buffer.size == 0

    def test_drain_does_not_alias_the_returned_list(self, rows_factory):
        """The writer holds the drained rows; a later add must not mutate them."""

        buffer = Buffer()
        buffer.add(rows_factory("likes", 1)[0])
        drained = buffer.drain()
        buffer.add(rows_factory("likes", 1)[0])

        assert len(drained) == 1

    def test_drain_of_an_empty_buffer(self):
        assert Buffer().drain() == []

    def test_refills_after_draining(self, rows_factory):
        buffer = Buffer()
        buffer.add(rows_factory("likes", 1)[0])
        buffer.drain()
        row = rows_factory("likes", 1)[0]
        buffer.add(row)

        assert buffer.size == row_bytes(row)

    def test_buffers_do_not_share_row_lists(self):
        """A mutable default would make every Buffer share one list."""

        first, second = Buffer(), Buffer()
        first.add({"a": 1})

        assert second.rows == []


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
        """Derived rather than counted, so draining one buffer stays consistent."""

        buffer_set = BufferSet()
        for record_type in RECORD_TYPES:
            buffer_set.add(record_type, rows_factory(record_type, 1)[0])
        buffer_set.buffers["likes"].drain()

        assert buffer_set.size == sum(b.size for b in buffer_set.buffers.values())

    def test_add_routes_to_the_matching_buffer(self, rows_factory):
        buffer_set = BufferSet()
        buffer_set.add("follows", rows_factory("follows", 1)[0])

        assert len(buffer_set.buffers["follows"].rows) == 1
        assert buffer_set.buffers["likes"].rows == []

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
    def test_writes_every_non_empty_buffer(self, filled, recorded_writes, tmp_path):
        flush(filled, tmp_path)

        assert dict(recorded_writes) == dict(zip(RECORD_TYPES, [1, 2, 3, 4]))

    def test_empty_buffers_write_nothing(self, rows_factory, recorded_writes, tmp_path):
        buffer_set = BufferSet()
        buffer_set.add("posts", rows_factory("posts", 1)[0])

        flush(buffer_set, tmp_path)

        assert [record_type for record_type, _ in recorded_writes] == ["posts"]

    def test_nothing_buffered_writes_nothing(self, recorded_writes, tmp_path):
        flush(BufferSet(), tmp_path)

        assert recorded_writes == []

    def test_buffers_are_empty_afterward(self, filled, recorded_writes, tmp_path):
        flush(filled, tmp_path)

        assert filled.size == 0
        for buffer in filled.buffers.values():
            assert buffer.rows == []

    def test_restarts_the_age_timer(self, filled, recorded_writes, tmp_path, monkeypatch):
        clock = [500.0]
        monkeypatch.setattr(buffer_module.time, "monotonic", lambda: clock[0])

        flush(filled, tmp_path)

        assert filled.last_flush == 500.0

    def test_timer_restarts_with_nothing_to_write(self, recorded_writes, tmp_path, monkeypatch):
        """A size-triggered flush must not leave a stale timer that fires next tick."""

        clock = [500.0]
        monkeypatch.setattr(buffer_module.time, "monotonic", lambda: clock[0])
        buffer_set = BufferSet()

        flush(buffer_set, tmp_path)

        assert buffer_set.last_flush == 500.0

    def test_rows_survive_a_write_failure(self, filled, monkeypatch, tmp_path):
        """Draining before the write succeeds would lose the batch."""

        def boom(record_type, rows, data_dir):
            raise OSError("disk full")

        monkeypatch.setattr(buffer_module, "write", boom)
        expected = {rt: len(b.rows) for rt, b in filled.buffers.items()}

        with pytest.raises(OSError, match="disk full"):
            flush(filled, tmp_path)

        assert {rt: len(b.rows) for rt, b in filled.buffers.items()} == expected

    def test_write_receives_the_rows_it_should(self, rows_factory, monkeypatch, tmp_path):
        seen: list[list[dict]] = []
        monkeypatch.setattr(
            buffer_module, "write", lambda rt, rows, data_dir: seen.append(list(rows))
        )
        rows = rows_factory("follows", 2)
        buffer_set = BufferSet()
        for row in rows:
            buffer_set.add("follows", row)

        flush(buffer_set, tmp_path)

        assert seen == [rows]
