"""Tests for the run loop wiring."""

import asyncio

import pytest

from bluesky_ingestion_jetstream import main as main_module
from bluesky_ingestion_jetstream.constants import RECORD_TYPES
from bluesky_ingestion_jetstream.main import run


@pytest.fixture
def wired(monkeypatch, rows_factory):
    """Drive `run` with a canned stream and record every flush."""

    flushes: list[dict[str, int]] = []

    def fake_flush(buffers, data_dir):
        flushes.append({rt: len(b.rows) for rt, b in buffers.buffers.items() if b.rows})
        for buffer in buffers.buffers.values():
            buffer.drain()
        buffers.mark_flushed()

    monkeypatch.setattr(main_module, "flush", fake_flush)

    def drive(stream_rows):
        async def fake_stream():
            for parsed in stream_rows:
                yield parsed

        monkeypatch.setattr(main_module, "stream_events", fake_stream)
        return flushes

    return drive


def rows_for(rows_factory, record_type, count):
    return [(record_type, row) for row in rows_factory(record_type, count)]


class TestRun:
    def test_consumes_the_whole_stream(self, wired, rows_factory, tmp_path, monkeypatch):
        flushes = wired(rows_for(rows_factory, "likes", 5))
        monkeypatch.setattr(
            main_module.BufferSet, "should_flush", lambda self: False, raising=False
        )

        asyncio.run(run(tmp_path))

        assert flushes == []

    def test_flushes_when_the_buffers_say_so(self, wired, rows_factory, tmp_path, monkeypatch):
        flushes = wired(rows_for(rows_factory, "likes", 3))
        calls = {"n": 0}

        def every_other(self):
            calls["n"] += 1
            return calls["n"] % 2 == 0

        monkeypatch.setattr(main_module.BufferSet, "should_flush", every_other, raising=False)

        asyncio.run(run(tmp_path))

        assert flushes == [{"likes": 2}]

    def test_routes_each_row_to_its_record_type(self, wired, rows_factory, tmp_path, monkeypatch):
        stream = [pair for rt in RECORD_TYPES for pair in rows_for(rows_factory, rt, 2)]
        flushes = wired(stream)
        monkeypatch.setattr(
            main_module.BufferSet,
            "should_flush",
            lambda self: self.size > 0 and len(self.buffers["follows"].rows) == 2,
            raising=False,
        )

        asyncio.run(run(tmp_path))

        assert flushes == [dict.fromkeys(RECORD_TYPES, 2)]

    def test_empty_stream_never_flushes(self, wired, tmp_path):
        flushes = wired([])

        asyncio.run(run(tmp_path))

        assert flushes == []

    def test_uses_the_real_thresholds_by_default(self, wired, rows_factory, tmp_path):
        """A handful of rows is nowhere near the size threshold."""

        flushes = wired(rows_for(rows_factory, "likes", 10))

        asyncio.run(run(tmp_path))

        assert flushes == []

    def test_passes_the_data_dir_through(self, monkeypatch, rows_factory, tmp_path):
        seen: list = []

        async def fake_stream():
            for parsed in rows_for(rows_factory, "likes", 1):
                yield parsed

        monkeypatch.setattr(main_module, "stream_events", fake_stream)
        monkeypatch.setattr(main_module, "flush", lambda buffers, data_dir: seen.append(data_dir))
        monkeypatch.setattr(main_module.BufferSet, "should_flush", lambda self: True, raising=False)

        asyncio.run(run(tmp_path))

        assert seen == [tmp_path]
