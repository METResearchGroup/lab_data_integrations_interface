import time

import pytest

from bluesky_backfill_app.aws.queue import Message
from bluesky_backfill_app.fetch_repos.constants import FLUSH_REASON_AGE, FLUSH_REASON_SIZE
from bluesky_backfill_app.fetch_repos.landing.writer import build_table
from bluesky_backfill_app.fetch_repos.storage.buffer import RepoBuffer, get_flush_summary
from bluesky_ingestion_jetstream.constants import FOLLOWS, LIKES, POSTS, REPOSTS


def message(did="did:plc:a"):
    return Message(did=did, run_id="run-1", handle=f"handle-{did}", receive_count=1)


def table(record_type, *uris):
    return build_table(record_type, [{"uri": uri, "did": "did:plc:a"} for uri in uris])


def uris(buffer, record_type):
    return [uri for t in buffer.tables[record_type] for uri in t.column("uri").to_pylist()]


def now():
    return time.monotonic()


def test_empty_buffer_never_flushes():
    buffer = RepoBuffer(max_size_bytes=1, max_age_seconds=0.0)

    assert buffer.should_flush() is False


def test_add_routes_tables_to_their_record_type():
    buffer = RepoBuffer()

    buffer.add(message(), {POSTS: table(POSTS, "p1", "p2"), LIKES: table(LIKES, "l1")}, now())

    assert uris(buffer, POSTS) == ["p1", "p2"]
    assert uris(buffer, LIKES) == ["l1"]
    assert buffer.tables[REPOSTS] == []
    assert buffer.tables[FOLLOWS] == []


def test_add_skips_empty_tables():
    buffer = RepoBuffer()

    buffer.add(message(), {POSTS: table(POSTS)}, now())

    assert buffer.tables[POSTS] == []
    assert buffer.size == 0


def test_add_holds_the_message():
    buffer = RepoBuffer()

    buffer.add(message("did:plc:a"), {}, now())
    buffer.add(message("did:plc:b"), {}, now())

    assert [m.did for m in buffer.messages] == ["did:plc:a", "did:plc:b"]


def test_a_repeated_did_keeps_its_message_but_not_its_rows():
    buffer = RepoBuffer()
    buffer.add(message(), {POSTS: table(POSTS, "p1")}, now())
    size = buffer.size

    buffer.add(message(), {POSTS: table(POSTS, "p1")}, now())

    assert uris(buffer, POSTS) == ["p1"]
    assert buffer.size == size
    assert len(buffer.messages) == 2


def test_a_repo_with_no_rows_still_flushes_on_age():
    buffer = RepoBuffer(max_age_seconds=0.0)

    buffer.add(message(), {}, now())

    assert buffer.should_flush() is True
    assert buffer.flush_reason() == FLUSH_REASON_AGE


def test_size_is_the_arrow_bytes_of_every_table():
    buffer = RepoBuffer()
    posts, follows = table(POSTS, "p1"), table(FOLLOWS, "f1")

    buffer.add(message(), {POSTS: posts, FOLLOWS: follows}, now())

    assert buffer.size == posts.nbytes + follows.nbytes
    assert buffer.size > 0


def test_flushes_on_size():
    buffer = RepoBuffer(max_size_bytes=1, max_age_seconds=3600.0)

    buffer.add(message(), {POSTS: table(POSTS, "p1")}, now())

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

    buffer.add(message(), {POSTS: table(POSTS, "p1")}, now())

    assert buffer.flush_reason() == FLUSH_REASON_SIZE


def test_flush_reason_raises_below_thresholds():
    buffer = RepoBuffer(max_age_seconds=3600.0)
    buffer.add(message(), {POSTS: table(POSTS, "p1")}, now())

    with pytest.raises(ValueError):
        buffer.flush_reason()


def test_clear_empties_everything_and_restarts_the_clock():
    buffer = RepoBuffer(max_age_seconds=60.0)
    buffer.add(message(), {POSTS: table(POSTS, "p1")}, now() - 61.0)

    buffer.clear()

    assert buffer.messages == []
    assert buffer.tables[POSTS] == []
    assert buffer.size == 0
    assert buffer.should_flush() is False

    buffer.add(message(), {POSTS: table(POSTS, "p1")}, now())
    assert uris(buffer, POSTS) == ["p1"]
    assert buffer.should_flush() is False


def test_clear_rebinds_what_was_handed_off():
    buffer = RepoBuffer()
    buffer.add(message(), {POSTS: table(POSTS, "p1")}, now())
    messages, tables = buffer.messages, buffer.tables

    buffer.clear()

    assert len(messages) == 1
    assert len(tables[POSTS]) == 1


def test_flush_summary_counts_repos_rows_and_bytes():
    buffer = RepoBuffer()
    posts, likes = table(POSTS, "p1", "p2"), table(LIKES, "l1")
    buffer.add(message("did:plc:a"), {POSTS: posts}, now())
    buffer.add(message("did:plc:b"), {LIKES: likes}, now())

    summary = get_flush_summary(buffer, FLUSH_REASON_SIZE)

    assert summary.reason == FLUSH_REASON_SIZE
    assert summary.repos == 2
    assert summary.rows == {POSTS: 2, LIKES: 1}
    assert summary.sizes == {POSTS: posts.nbytes, LIKES: likes.nbytes}


def test_flush_summary_survives_clear():
    buffer = RepoBuffer()
    buffer.add(message(), {POSTS: table(POSTS, "p1")}, now())

    summary = get_flush_summary(buffer, FLUSH_REASON_AGE)
    buffer.clear()

    assert summary.repos == 1
    assert summary.rows == {POSTS: 1}
