"""Tests for the run loop wiring."""

import asyncio
from contextlib import suppress

import pytest

from bluesky_ingestion_jetstream import main as main_module
from bluesky_ingestion_jetstream.constants import CURSOR_REWIND_MICROSECONDS, RECORD_TYPES
from bluesky_ingestion_jetstream.main import flush_loop, run
from bluesky_ingestion_jetstream.network.connection import StreamEvent
from bluesky_ingestion_jetstream.storage.buffer import BufferSet
from bluesky_ingestion_jetstream.storage.cursor import CursorTracker
from tests.bluesky_ingestion_jetstream.conftest import TIME_US, MemoryCursorStore, MemorySink


def stream_of(events):
    """A stream that yields to the loop between events, letting flush ticks land.

    Without the sleeps the read loop would consume the whole list in one step and
    the flush task would never get to run.
    """

    async def fake_stream(resume_from=lambda: None):
        for event in events:
            await asyncio.sleep(0)
            yield event
        await asyncio.sleep(0)

    return fake_stream


def drive(sink, tracker):
    """Run with a zero flush interval, so one tick lands between events."""

    asyncio.run(run(sink, tracker, flush_interval=0))


@pytest.fixture
def wired(monkeypatch):
    """Drive `run` with a canned stream and record every flush."""

    flushes: list[dict[str, int]] = []

    def fake_flush(buffers, sink):
        flushes.append({rt: len(b.rows) for rt, b in buffers.buffers.items() if b.rows})
        for buffer in buffers.buffers.values():
            buffer.clear()
        buffers.mark_flushed()

    monkeypatch.setattr(main_module, "flush", fake_flush)

    def wire(stream_events):
        monkeypatch.setattr(main_module, "stream_events", stream_of(stream_events))
        return flushes

    return wire


@pytest.fixture
def sink() -> MemorySink:
    """`run` needs a destination; these tests stub `flush`, so it is never used."""

    return MemorySink()


@pytest.fixture
def store() -> MemoryCursorStore:
    return MemoryCursorStore()


@pytest.fixture
def tracker(store) -> CursorTracker:
    return CursorTracker(store)


def rows_for(rows_factory, record_type, count):
    return [
        StreamEvent(TIME_US + index, (record_type, row))
        for index, row in enumerate(rows_factory(record_type, count))
    ]


async def tick(buffers, sink, tracker, times=1):
    """Run `flush_loop` for `times` checks, then stop it."""

    task = asyncio.create_task(flush_loop(buffers, sink, tracker, 0))
    # Two yields per check: one for the task's sleep, one for the check itself.
    for _ in range(2 * times):
        await asyncio.sleep(0)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


class TestRun:
    def test_consumes_the_whole_stream(self, wired, rows_factory, sink, tracker, monkeypatch):
        flushes = wired(rows_for(rows_factory, "likes", 5))
        monkeypatch.setattr(
            main_module.BufferSet, "should_flush", lambda self: False, raising=False
        )

        drive(sink, tracker)

        assert flushes == []

    def test_flushes_when_the_buffers_say_so(self, wired, rows_factory, sink, tracker, monkeypatch):
        flushes = wired(rows_for(rows_factory, "likes", 3))
        calls = {"n": 0}

        def every_other(self):
            calls["n"] += 1
            return calls["n"] % 2 == 0

        monkeypatch.setattr(main_module.BufferSet, "should_flush", every_other, raising=False)

        drive(sink, tracker)

        assert flushes == [{"likes": 2}]

    def test_routes_each_row_to_its_record_type(
        self, wired, rows_factory, sink, tracker, monkeypatch
    ):
        stream = [event for rt in RECORD_TYPES for event in rows_for(rows_factory, rt, 2)]
        flushes = wired(stream)
        monkeypatch.setattr(
            main_module.BufferSet,
            "should_flush",
            lambda self: self.size > 0 and len(self.buffers["follows"].rows) == 2,
            raising=False,
        )

        drive(sink, tracker)

        assert flushes == [dict.fromkeys(RECORD_TYPES, 2)]

    def test_empty_stream_never_flushes(self, wired, sink, tracker):
        flushes = wired([])

        drive(sink, tracker)

        assert flushes == []

    def test_uses_the_real_thresholds_by_default(self, wired, rows_factory, sink, tracker):
        """A handful of rows is nowhere near the size threshold."""

        flushes = wired(rows_for(rows_factory, "likes", 10))

        drive(sink, tracker)

        assert flushes == []

    def test_passes_the_sink_through_to_flush(self, monkeypatch, rows_factory, sink, tracker):
        seen: list = []

        monkeypatch.setattr(
            main_module, "stream_events", stream_of(rows_for(rows_factory, "likes", 1))
        )
        monkeypatch.setattr(main_module, "flush", lambda buffers, s: seen.append(s))
        monkeypatch.setattr(main_module.BufferSet, "should_flush", lambda self: True, raising=False)

        drive(sink, tracker)

        assert sink in seen

    def test_hands_the_resume_cursor_to_the_stream(self, monkeypatch, rows_factory, sink):
        seen: list = []
        events = rows_for(rows_factory, "likes", 1)

        async def fake_stream(resume_from=lambda: None):
            seen.append(resume_from())
            for event in events:
                await asyncio.sleep(0)
                yield event

        monkeypatch.setattr(main_module, "stream_events", fake_stream)
        tracker = CursorTracker(MemoryCursorStore(stored=TIME_US))

        drive(sink, tracker)

        assert seen == [TIME_US - CURSOR_REWIND_MICROSECONDS]


class TestFlushLoop:
    """The timer path, driven without a stream at all."""

    def test_flushes_a_quiet_buffer(self, rows_factory, sink, tracker, monkeypatch):
        """The point of the timer: rows land with no further events arriving."""

        rows = rows_factory("likes", 2)
        buffers = BufferSet()
        for row in rows:
            buffers.add("likes", row)
        monkeypatch.setattr(BufferSet, "should_flush", lambda self: True, raising=False)

        asyncio.run(tick(buffers, sink, tracker))

        assert sink.writes == [("likes", rows)]
        assert buffers.buffers["likes"].rows == []

    def test_does_not_flush_below_the_thresholds(self, rows_factory, sink, tracker):
        buffers = BufferSet()
        for row in rows_factory("likes", 2):
            buffers.add("likes", row)

        asyncio.run(tick(buffers, sink, tracker, times=3))

        assert sink.writes == []
        assert len(buffers.buffers["likes"].rows) == 2

    def test_advances_the_cursor_after_flushing(self, rows_factory, sink, store, monkeypatch):
        tracker = CursorTracker(store)
        tracker.observe(TIME_US)
        buffers = BufferSet()
        for row in rows_factory("likes", 1):
            buffers.add("likes", row)
        monkeypatch.setattr(BufferSet, "should_flush", lambda self: True, raising=False)

        asyncio.run(tick(buffers, sink, tracker))

        assert store.writes == [TIME_US]


class TestCursor:
    def test_does_not_advance_without_a_flush(
        self, wired, rows_factory, sink, tracker, store, monkeypatch
    ):
        """The invariant: the cursor must never be ahead of an unwritten event."""

        wired(rows_for(rows_factory, "likes", 5))
        monkeypatch.setattr(
            main_module.BufferSet, "should_flush", lambda self: False, raising=False
        )

        drive(sink, tracker)

        assert store.writes == []

    def test_advances_once_the_buffers_have_flushed(
        self, wired, rows_factory, sink, tracker, store, monkeypatch
    ):
        stream = rows_for(rows_factory, "likes", 3)
        wired(stream)
        monkeypatch.setattr(main_module.BufferSet, "should_flush", lambda self: True, raising=False)

        drive(sink, tracker)

        assert store.writes[-1] == stream[-1].time_us

    def test_a_failed_flush_stops_the_run_and_leaves_the_cursor_behind(
        self, monkeypatch, rows_factory, sink, tracker, store
    ):
        """Rows that reached neither Iceberg nor the dead letter must be replayed."""

        def boom(buffers, s):
            raise RuntimeError("dead letter unavailable")

        monkeypatch.setattr(
            main_module, "stream_events", stream_of(rows_for(rows_factory, "likes", 2))
        )
        monkeypatch.setattr(main_module, "flush", boom)
        monkeypatch.setattr(main_module.BufferSet, "should_flush", lambda self: True, raising=False)

        with pytest.raises(RuntimeError, match="dead letter unavailable"):
            drive(sink, tracker)

        assert store.writes == []

    def test_dropped_events_still_advance_the_cursor(
        self, wired, sink, tracker, store, monkeypatch
    ):
        """Otherwise a quiet spell for our four collections stalls the cursor."""

        wired([StreamEvent(TIME_US, None), StreamEvent(TIME_US + 1, None)])
        monkeypatch.setattr(main_module.BufferSet, "should_flush", lambda self: True, raising=False)

        drive(sink, tracker)

        assert store.writes == [TIME_US, TIME_US + 1]


class TestNewRunId:
    def test_is_a_distinct_value_each_call(self):
        """Two processes must not share a run id, or the column cannot separate them."""

        assert main_module.new_run_id() != main_module.new_run_id()
