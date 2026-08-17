"""Tests for the resume cursor: when it advances, and when it must not."""

import logging

from bluesky_ingestion_jetstream.constants import CURSOR_REWIND_MICROSECONDS
from bluesky_ingestion_jetstream.storage import cursor as cursor_module
from bluesky_ingestion_jetstream.storage.cursor import CursorTracker
from tests.bluesky_ingestion_jetstream.conftest import MemoryCursorStore

EARLY = 1784789293411372
LATE = EARLY + 1_000_000


class TestObserve:
    def test_nothing_is_persisted_before_a_flush(self):
        """The whole point: an unwritten event must never be behind the cursor."""

        store = MemoryCursorStore()
        tracker = CursorTracker(store)

        tracker.observe(EARLY)
        tracker.observe(LATE)

        assert store.writes == []
        assert tracker.cursor_value is None

    def test_keeps_the_high_water_mark(self):
        tracker = CursorTracker(MemoryCursorStore())

        tracker.observe(LATE)
        tracker.observe(EARLY)

        assert tracker.most_recent_event_timestamp == LATE

    def test_a_replay_does_not_drag_the_cursor_backwards(self):
        """A reconnect redelivers events already accounted for."""

        store = MemoryCursorStore()
        tracker = CursorTracker(store)
        tracker.observe(LATE)
        tracker.mark_flushed()

        tracker.observe(EARLY)
        tracker.mark_flushed()

        assert store.writes == [LATE]


class TestMarkFlushed:
    def test_persists_everything_seen(self):
        store = MemoryCursorStore()
        tracker = CursorTracker(store)

        tracker.observe(EARLY)
        tracker.mark_flushed()

        assert store.writes == [EARLY]
        assert tracker.cursor_value == EARLY

    def test_an_empty_stream_writes_nothing(self):
        store = MemoryCursorStore()

        CursorTracker(store).mark_flushed()

        assert store.writes == []

    def test_does_not_rewrite_an_unchanged_cursor(self):
        """Flushes are frequent; rewriting the same value is a needless request."""

        store = MemoryCursorStore()
        tracker = CursorTracker(store)
        tracker.observe(EARLY)

        tracker.mark_flushed()
        tracker.mark_flushed()

        assert store.writes == [EARLY]

    def test_a_failed_write_leaves_the_stored_cursor_alone(self, caplog):
        """Costs a longer replay, not correctness, so it must not raise."""

        tracker = CursorTracker(MemoryCursorStore(error=RuntimeError("dynamodb down")))
        tracker.observe(EARLY)

        with caplog.at_level(logging.WARNING):
            tracker.mark_flushed()

        assert tracker.cursor_value is None
        assert "cursor write failed" in caplog.text

    def test_a_later_flush_supersedes_a_failed_one(self):
        store = MemoryCursorStore(error=RuntimeError("dynamodb down"))
        tracker = CursorTracker(store)
        tracker.observe(EARLY)
        tracker.mark_flushed()

        store.error = None
        tracker.observe(LATE)
        tracker.mark_flushed()

        assert store.writes == [LATE]


class TestResumeFrom:
    def test_a_cold_start_has_no_cursor(self):
        assert CursorTracker(MemoryCursorStore()).resume_from() is None

    def test_picks_up_where_the_last_run_left_off(self):
        tracker = CursorTracker(MemoryCursorStore(stored=LATE))

        assert tracker.resume_from() == LATE - CURSOR_REWIND_MICROSECONDS

    def test_resumes_at_the_observed_position(self):
        """No rewind, so a reconnect replays nothing it has already buffered."""

        tracker = CursorTracker(MemoryCursorStore())
        tracker.observe(LATE)
        tracker.mark_flushed()

        assert tracker.resume_from() == LATE

    def test_never_goes_negative(self, monkeypatch):
        """The clamp is inert at a zero rewind, but has to hold if one returns."""

        monkeypatch.setattr(cursor_module, "CURSOR_REWIND_MICROSECONDS", 5_000_000)
        tracker = CursorTracker(MemoryCursorStore(stored=1))

        assert tracker.resume_from() == 0

    def test_tracks_the_cursor_as_it_advances(self):
        """Read per reconnect, so a mid-run advance has to be visible here."""

        tracker = CursorTracker(MemoryCursorStore(stored=EARLY))
        tracker.observe(LATE)
        tracker.mark_flushed()

        assert tracker.resume_from() == LATE - CURSOR_REWIND_MICROSECONDS

    def test_does_not_replay_events_still_held_in_the_buffers(self):
        """A reconnect keeps the buffers, so re-reading what they hold only duplicates it."""

        tracker = CursorTracker(MemoryCursorStore(stored=EARLY))
        tracker.observe(LATE)

        assert tracker.resume_from() == LATE - CURSOR_REWIND_MICROSECONDS

    def test_a_restart_resumes_from_the_persisted_cursor(self):
        """Nothing is in memory yet, so the durable position is the only safe one."""

        tracker = CursorTracker(MemoryCursorStore(stored=EARLY))

        assert tracker.resume_from() == EARLY - CURSOR_REWIND_MICROSECONDS

    def test_a_failed_cursor_write_does_not_widen_the_replay(self):
        """The rows flushed during the outage are committed; re-reading them is waste."""

        tracker = CursorTracker(
            MemoryCursorStore(stored=EARLY, error=RuntimeError("dynamodb down"))
        )
        tracker.observe(LATE)
        tracker.mark_flushed()

        assert tracker.cursor_value == EARLY
        assert tracker.resume_from() == LATE - CURSOR_REWIND_MICROSECONDS
