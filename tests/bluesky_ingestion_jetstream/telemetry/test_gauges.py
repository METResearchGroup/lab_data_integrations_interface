"""Tests for the pulled gauges.

The callbacks run on the reader's thread long after registration, so what
matters is that they read live values rather than a snapshot taken at startup.
"""

import pytest

from bluesky_ingestion_jetstream.storage.cursor import CursorTracker
from bluesky_ingestion_jetstream.telemetry import gauges as gauges_module
from bluesky_ingestion_jetstream.telemetry.gauges import (
    observe_connected,
    observe_cursor,
    register_cursor_tracker,
)
from bluesky_ingestion_jetstream.telemetry.state import STREAM_STATE
from tests.bluesky_ingestion_jetstream.conftest import TIME_US, MemoryCursorStore


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    """Both gauges read module state; leaking it would couple the tests."""

    monkeypatch.setattr(gauges_module, "_tracker", None)
    monkeypatch.setattr(STREAM_STATE, "connected", False)


def values(observations) -> list[float]:
    return [observation.value for observation in observations]


class TestObserveCursor:
    def test_reports_nothing_before_registration(self):
        assert values(observe_cursor(None)) == []

    def test_reports_nothing_when_no_cursor_is_stored(self):
        """A fresh environment has no cursor; a zero would read as 1970."""

        register_cursor_tracker(CursorTracker(MemoryCursorStore(stored=None)))

        assert values(observe_cursor(None)) == []

    def test_converts_microseconds_to_unix_seconds(self):
        register_cursor_tracker(CursorTracker(MemoryCursorStore(stored=TIME_US)))

        assert values(observe_cursor(None)) == [TIME_US / 1_000_000]

    def test_follows_the_tracker_after_registration(self):
        """Registration takes the object, not its value at the time."""

        tracker = CursorTracker(MemoryCursorStore(stored=TIME_US))
        register_cursor_tracker(tracker)

        tracker.observe(TIME_US + 5_000_000)
        tracker.mark_flushed()

        assert values(observe_cursor(None)) == [(TIME_US + 5_000_000) / 1_000_000]


class TestObserveConnected:
    def test_zero_while_disconnected(self):
        assert values(observe_connected(None)) == [0]

    def test_one_while_connected(self, monkeypatch):
        monkeypatch.setattr(STREAM_STATE, "connected", True)

        assert values(observe_connected(None)) == [1]
