import pytest

from bluesky_backfill_app.constants import FLUSH_REASON_AGE, FLUSH_REASON_COUNT
from bluesky_backfill_app.storage.buffer import DidBuffer


def test_add_dedupes_within_the_window():
    buffer = DidBuffer(max_dids=10)

    buffer.add("did:plc:a")
    buffer.add("did:plc:a")
    buffer.add("did:plc:b")

    assert buffer.dids == ["did:plc:a", "did:plc:b"]
    assert len(buffer) == 2


def test_empty_buffer_never_flushes():
    buffer = DidBuffer(max_dids=1, max_age_seconds=0.0)

    assert buffer.should_flush() is False


def test_flushes_on_count():
    buffer = DidBuffer(max_dids=2, max_age_seconds=3600.0)

    buffer.add("did:plc:a")
    assert buffer.should_flush() is False

    buffer.add("did:plc:b")
    assert buffer.should_flush() is True
    assert buffer.flush_reason() == FLUSH_REASON_COUNT


def test_flushes_on_age():
    buffer = DidBuffer(max_dids=1000, max_age_seconds=0.0)

    buffer.add("did:plc:a")

    assert buffer.should_flush() is True
    assert buffer.flush_reason() == FLUSH_REASON_AGE


def test_count_wins_when_both_thresholds_trip():
    buffer = DidBuffer(max_dids=1, max_age_seconds=0.0)

    buffer.add("did:plc:a")

    assert buffer.flush_reason() == FLUSH_REASON_COUNT


def test_flush_reason_raises_below_thresholds():
    buffer = DidBuffer(max_dids=10, max_age_seconds=3600.0)
    buffer.add("did:plc:a")

    with pytest.raises(ValueError):
        buffer.flush_reason()


def test_clear_drops_dedupe_state_and_restarts_the_timer():
    buffer = DidBuffer(max_dids=10, max_age_seconds=3600.0)
    buffer.add("did:plc:a")

    buffer.clear()
    buffer.add("did:plc:a")

    assert buffer.dids == ["did:plc:a"]
    assert buffer.should_flush() is False


def test_clear_rebinds_rather_than_mutating():
    buffer = DidBuffer()
    buffer.add("did:plc:a")
    handed_off = buffer.dids

    buffer.clear()

    assert handed_off == ["did:plc:a"]
