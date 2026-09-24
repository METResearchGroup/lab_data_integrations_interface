import time

import pytest

from bluesky_backfill_app.aws.queue import Message
from bluesky_backfill_app.fetch_repos.constants import FLUSH_REASON_AGE, FLUSH_REASON_SIZE
from bluesky_backfill_app.fetch_repos.storage.buffer import RepoBuffer, get_flush_summary
from bluesky_ingestion_jetstream.constants import FOLLOWS, LIKES, POSTS, REPOSTS


def message(did="did:plc:a"):
    return Message(did=did, run_id="run-1", handle=f"handle-{did}", receive_count=1)


def row(uri):
    return {"uri": uri, "did": "did:plc:a"}


def now():
    return time.monotonic()


def test_empty_buffer_never_flushes():
    buffer = RepoBuffer(max_size_bytes=1, max_age_seconds=0.0)

    assert buffer.should_flush() is False


def test_add_routes_rows_to_their_record_type():
    buffer = RepoBuffer()

    buffer.add(message(), {POSTS: [row("p1"), row("p2")], LIKES: [row("l1")]}, now())

    assert [r["uri"] for r in buffer.buffers[POSTS].rows] == ["p1", "p2"]
    assert [r["uri"] for r in buffer.buffers[LIKES].rows] == ["l1"]
    assert buffer.buffers[REPOSTS].rows == []
    assert buffer.buffers[FOLLOWS].rows == []


def test_add_holds_the_message():
    buffer = RepoBuffer()

    buffer.add(message("did:plc:a"), {}, now())
    buffer.add(message("did:plc:b"), {}, now())

    assert [m.did for m in buffer.messages] == ["did:plc:a", "did:plc:b"]


def test_a_repo_with_no_rows_still_flushes_on_age():
    buffer = RepoBuffer(max_age_seconds=0.0)

    buffer.add(message(), {}, now())

    assert buffer.should_flush() is True
    assert buffer.flush_reason() == FLUSH_REASON_AGE


def test_size_sums_every_record_type():
    buffer = RepoBuffer()

    buffer.add(message(), {POSTS: [row("p1")], FOLLOWS: [row("f1")]}, now())

    assert buffer.size == buffer.buffers[POSTS].size + buffer.buffers[FOLLOWS].size
    assert buffer.size > 0


def test_flushes_on_size():
    buffer = RepoBuffer(max_size_bytes=1, max_age_seconds=3600.0)

    buffer.add(message(), {POSTS: [row("p1")]}, now())

    assert buffer.should_flush() is True
    assert buffer.flush_reason() == FLUSH_REASON_SIZE


def test_age_runs_from_the_receive_not_the_add():
    buffer = RepoBuffer(max_age_seconds=60.0)

    buffer.add(message(), {}, now() - 61.0)

    assert buffer.flush_reason() == FLUSH_REASON_AGE


def test_age_runs_from_the_oldest_receive():
    buffer = RepoBuffer(max_age_seconds=60.0)

    buffer.add(message("did:plc:a"), {}, now() - 61.0)
    buffer.add(message("did:plc:b"), {}, now())

    assert buffer.should_flush() is True


def test_size_wins_when_both_thresholds_trip():
    buffer = RepoBuffer(max_size_bytes=1, max_age_seconds=0.0)

    buffer.add(message(), {POSTS: [row("p1")]}, now())

    assert buffer.flush_reason() == FLUSH_REASON_SIZE


def test_flush_reason_raises_below_thresholds():
    buffer = RepoBuffer(max_age_seconds=3600.0)
    buffer.add(message(), {POSTS: [row("p1")]}, now())

    with pytest.raises(ValueError):
        buffer.flush_reason()


def test_clear_empties_everything_and_restarts_the_clock():
    buffer = RepoBuffer(max_age_seconds=60.0)
    buffer.add(message(), {POSTS: [row("p1")]}, now() - 61.0)

    buffer.clear()

    assert buffer.messages == []
    assert buffer.size == 0
    assert buffer.should_flush() is False

    buffer.add(message(), {}, now())
    assert buffer.should_flush() is False


def test_clear_rebinds_the_messages():
    buffer = RepoBuffer()
    buffer.add(message(), {}, now())
    handed_off = buffer.messages

    buffer.clear()

    assert len(handed_off) == 1


def test_flush_summary_counts_repos_rows_and_bytes():
    buffer = RepoBuffer()
    buffer.add(message("did:plc:a"), {POSTS: [row("p1"), row("p2")]}, now())
    buffer.add(message("did:plc:b"), {LIKES: [row("l1")]}, now())

    summary = get_flush_summary(buffer, FLUSH_REASON_SIZE)

    assert summary.reason == FLUSH_REASON_SIZE
    assert summary.repos == 2
    assert summary.rows == {POSTS: 2, LIKES: 1}
    assert summary.sizes == {POSTS: buffer.buffers[POSTS].size, LIKES: buffer.buffers[LIKES].size}


def test_flush_summary_survives_clear():
    buffer = RepoBuffer()
    buffer.add(message(), {POSTS: [row("p1")]}, now())

    summary = get_flush_summary(buffer, FLUSH_REASON_AGE)
    buffer.clear()

    assert summary.repos == 1
    assert summary.rows == {POSTS: 1}
