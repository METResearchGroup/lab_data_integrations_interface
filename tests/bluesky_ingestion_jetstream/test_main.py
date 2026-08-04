"""Tests for the run loop wiring."""

import asyncio

import pytest

from bluesky_ingestion_jetstream import main as main_module
from bluesky_ingestion_jetstream.constants import CURSOR_REWIND_MICROSECONDS, RECORD_TYPES
from bluesky_ingestion_jetstream.main import run
from bluesky_ingestion_jetstream.network.connection import StreamEvent
from bluesky_ingestion_jetstream.storage.cursor import CursorTracker
from tests.bluesky_ingestion_jetstream.conftest import TIME_US, MemoryCursorStore, MemorySink


@pytest.fixture
def wired(monkeypatch, rows_factory):
    """Drive `run` with a canned stream and record every flush."""

    flushes: list[dict[str, int]] = []

    def fake_flush(buffers, sink):
        flushes.append({rt: len(b.rows) for rt, b in buffers.buffers.items() if b.rows})
        for buffer in buffers.buffers.values():
            buffer.clear()
        buffers.mark_flushed()

    monkeypatch.setattr(main_module, "flush", fake_flush)

    def drive(stream_events):
        async def fake_stream(resume_from=lambda: None):
            for event in stream_events:
                yield event

        monkeypatch.setattr(main_module, "stream_events", fake_stream)
        return flushes

    return drive


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


class TestRun:
    def test_consumes_the_whole_stream(self, wired, rows_factory, sink, tracker, monkeypatch):
        flushes = wired(rows_for(rows_factory, "likes", 5))
        monkeypatch.setattr(
            main_module.BufferSet, "should_flush", lambda self: False, raising=False
        )

        asyncio.run(run(sink, tracker))

        assert flushes == []

    def test_flushes_when_the_buffers_say_so(self, wired, rows_factory, sink, tracker, monkeypatch):
        flushes = wired(rows_for(rows_factory, "likes", 3))
        calls = {"n": 0}

        def every_other(self):
            calls["n"] += 1
            return calls["n"] % 2 == 0

        monkeypatch.setattr(main_module.BufferSet, "should_flush", every_other, raising=False)

        asyncio.run(run(sink, tracker))

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

        asyncio.run(run(sink, tracker))

        assert flushes == [dict.fromkeys(RECORD_TYPES, 2)]

    def test_empty_stream_never_flushes(self, wired, sink, tracker):
        flushes = wired([])

        asyncio.run(run(sink, tracker))

        assert flushes == []

    def test_uses_the_real_thresholds_by_default(self, wired, rows_factory, sink, tracker):
        """A handful of rows is nowhere near the size threshold."""

        flushes = wired(rows_for(rows_factory, "likes", 10))

        asyncio.run(run(sink, tracker))

        assert flushes == []

    def test_passes_the_sink_through_to_flush(self, monkeypatch, rows_factory, sink, tracker):
        seen: list = []

        async def fake_stream(resume_from=lambda: None):
            for event in rows_for(rows_factory, "likes", 1):
                yield event

        monkeypatch.setattr(main_module, "stream_events", fake_stream)
        monkeypatch.setattr(main_module, "flush", lambda buffers, s: seen.append(s))
        monkeypatch.setattr(main_module.BufferSet, "should_flush", lambda self: True, raising=False)

        asyncio.run(run(sink, tracker))

        assert seen == [sink]


class TestCursor:
    def test_does_not_advance_without_a_flush(
        self, wired, rows_factory, sink, tracker, store, monkeypatch
    ):
        """The invariant: the cursor must never be ahead of an unwritten event."""

        wired(rows_for(rows_factory, "likes", 5))
        monkeypatch.setattr(
            main_module.BufferSet, "should_flush", lambda self: False, raising=False
        )

        asyncio.run(run(sink, tracker))

        assert store.writes == []

    def test_advances_once_the_buffers_have_flushed(
        self, wired, rows_factory, sink, tracker, store, monkeypatch
    ):
        stream = rows_for(rows_factory, "likes", 3)
        wired(stream)
        monkeypatch.setattr(main_module.BufferSet, "should_flush", lambda self: True, raising=False)

        asyncio.run(run(sink, tracker))

        assert store.writes[-1] == stream[-1].time_us

    def test_a_failed_flush_leaves_the_cursor_behind(
        self, monkeypatch, rows_factory, sink, tracker, store
    ):
        """Rows that reached neither Iceberg nor the dead letter must be replayed."""

        async def fake_stream(resume_from=lambda: None):
            for event in rows_for(rows_factory, "likes", 2):
                yield event

        def boom(buffers, s):
            raise RuntimeError("dead letter unavailable")

        monkeypatch.setattr(main_module, "stream_events", fake_stream)
        monkeypatch.setattr(main_module, "flush", boom)
        monkeypatch.setattr(main_module.BufferSet, "should_flush", lambda self: True, raising=False)

        with pytest.raises(RuntimeError, match="dead letter unavailable"):
            asyncio.run(run(sink, tracker))

        assert store.writes == []

    def test_dropped_events_still_advance_the_cursor(
        self, wired, sink, tracker, store, monkeypatch
    ):
        """Otherwise a quiet spell for our four collections stalls the cursor."""

        wired([StreamEvent(TIME_US, None), StreamEvent(TIME_US + 1, None)])
        monkeypatch.setattr(main_module.BufferSet, "should_flush", lambda self: True, raising=False)

        asyncio.run(run(sink, tracker))

        assert store.writes == [TIME_US, TIME_US + 1]

    def test_hands_the_resume_cursor_to_the_stream(self, monkeypatch, rows_factory, sink):
        seen: list = []

        async def fake_stream(resume_from=lambda: None):
            seen.append(resume_from())
            for event in rows_for(rows_factory, "likes", 1):
                yield event

        monkeypatch.setattr(main_module, "stream_events", fake_stream)
        tracker = CursorTracker(MemoryCursorStore(stored=TIME_US))

        asyncio.run(run(sink, tracker))

        assert seen == [TIME_US - CURSOR_REWIND_MICROSECONDS]


class TestNewRunId:
    def test_is_a_distinct_value_each_call(self):
        """Two processes must not share a run id, or the column cannot separate them."""

        assert main_module.new_run_id() != main_module.new_run_id()
