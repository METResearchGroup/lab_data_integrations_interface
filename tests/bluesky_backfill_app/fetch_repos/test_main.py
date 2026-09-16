import pytest

from bluesky_backfill_app.aws.constants import (
    MAX_RECEIVE_COUNT,
    REASON_ACCOUNT_TAKENDOWN,
    REASON_LANDING_WRITE_ERROR,
    STATUS_DEAD_LETTERED,
    STATUS_DONE,
    STATUS_FAILED,
)
from bluesky_backfill_app.aws.queue import Message
from bluesky_backfill_app.fetch_repos.failures import RepoFailure
from bluesky_backfill_app.fetch_repos.main import flush, process_message, run
from bluesky_backfill_app.fetch_repos.storage.buffer import RepoBuffer
from bluesky_ingestion_jetstream.constants import LIKES

MAIN = "bluesky_backfill_app.fetch_repos.main"


class FakeDidStore:
    def __init__(self, events, fail_done=False):
        self.events = events
        self.fail_done = fail_done

    def set_failed(self, did, status, error, reason):
        self.events.append(("set_failed", did, status, reason))

    def set_status_many(self, dids, status):
        if self.fail_done:
            raise RuntimeError("dynamodb down")
        self.events.append(("set_status_many", dids, status))


class FakeQueue:
    """Serves `messages`, then raises KeyboardInterrupt as SIGTERM would."""

    def __init__(self, events, messages=()):
        self.events = events
        self.messages = list(messages)

    def receive(self):
        if not self.messages:
            raise KeyboardInterrupt
        return self.messages.pop(0)

    def delete(self, handle):
        self.events.append(("delete", handle))

    def delete_many(self, handles):
        self.events.append(("delete_many", handles))
        return []


def message(did, receive_count=1):
    return Message(did=did, run_id=None, handle=f"handle-{did}", receive_count=receive_count)


def rows_for(did):
    return {LIKES: [{"uri": f"at://{did}/app.bsky.feed.like/1", "did": did}]}


def big_buffer():
    return RepoBuffer(max_size_bytes=10**12, max_age_seconds=10**9)


@pytest.fixture
def events(monkeypatch):
    events = []

    def write_buffer(buffer, run_id):
        events.append(("write", [m.did for m in buffer.messages]))
        return ["path"]

    monkeypatch.setattr(f"{MAIN}.write_buffer", write_buffer)
    monkeypatch.setattr(f"{MAIN}.load_repo", rows_for)
    return events


def test_process_message_buffers_a_loaded_repo(events):
    buffer = big_buffer()

    process_message(message("did:plc:a"), FakeDidStore(events), FakeQueue(events), buffer, 0.0)

    assert [m.did for m in buffer.messages] == ["did:plc:a"]
    assert len(buffer.buffers[LIKES].rows) == 1
    assert events == []


def test_process_message_records_a_failure_instead_of_buffering(events, monkeypatch):
    def load_repo(did):
        raise RepoFailure(REASON_ACCOUNT_TAKENDOWN, ValueError())

    monkeypatch.setattr(f"{MAIN}.load_repo", load_repo)
    buffer = big_buffer()

    process_message(message("did:plc:a"), FakeDidStore(events), FakeQueue(events), buffer, 0.0)

    assert buffer.messages == []
    assert events == [
        ("set_failed", "did:plc:a", STATUS_FAILED, REASON_ACCOUNT_TAKENDOWN),
        ("delete", "handle-did:plc:a"),
    ]


def fill(buffer, *messages):
    for msg in messages:
        buffer.add(msg, rows_for(msg.did), 0.0)


def test_flush_writes_then_marks_done_then_acks(events):
    buffer = big_buffer()
    fill(buffer, message("did:plc:a"), message("did:plc:b"))

    flush(buffer, FakeDidStore(events), FakeQueue(events), "run-1", "size")

    assert events == [
        ("write", ["did:plc:a", "did:plc:b"]),
        ("set_status_many", ["did:plc:a", "did:plc:b"], STATUS_DONE),
        ("delete_many", ["handle-did:plc:a", "handle-did:plc:b"]),
    ]
    assert buffer.messages == []


def test_a_failed_write_drops_the_buffer_without_acking(events, monkeypatch):
    def write_buffer(buffer, run_id):
        raise OSError("s3 down")

    monkeypatch.setattr(f"{MAIN}.write_buffer", write_buffer)
    buffer = big_buffer()
    fill(buffer, message("did:plc:a"), message("did:plc:b", receive_count=MAX_RECEIVE_COUNT))

    flush(buffer, FakeDidStore(events), FakeQueue(events), "run-1", "size")

    assert events == [
        ("set_failed", "did:plc:b", STATUS_DEAD_LETTERED, REASON_LANDING_WRITE_ERROR),
    ]
    assert buffer.messages == []


def test_a_failed_done_write_drops_the_buffer_without_acking(events):
    buffer = big_buffer()
    fill(buffer, message("did:plc:a"))

    flush(buffer, FakeDidStore(events, fail_done=True), FakeQueue(events), "run-1", "size")

    assert events == [("write", ["did:plc:a"])]
    assert buffer.messages == []


def test_run_flushes_when_the_buffer_trips_a_threshold(events):
    queue = FakeQueue(events, [message("did:plc:a"), None, message("did:plc:b")])

    with pytest.raises(KeyboardInterrupt):
        run(FakeDidStore(events), queue, RepoBuffer(max_size_bytes=1), "run-1")

    assert [event for event in events if event[0] == "write"] == [
        ("write", ["did:plc:a"]),
        ("write", ["did:plc:b"]),
    ]


def test_run_flushes_what_is_buffered_when_stopped(events):
    queue = FakeQueue(events, [message("did:plc:a"), message("did:plc:b")])

    with pytest.raises(KeyboardInterrupt):
        run(FakeDidStore(events), queue, big_buffer(), "run-1")

    assert events[-1] == ("delete_many", ["handle-did:plc:a", "handle-did:plc:b"])


def test_run_does_not_flush_an_empty_buffer_when_stopped(events):
    with pytest.raises(KeyboardInterrupt):
        run(FakeDidStore(events), FakeQueue(events), big_buffer(), "run-1")

    assert events == []


def test_run_abandons_the_in_flight_repo_when_stopped(events, monkeypatch):
    def load_repo(did):
        if did == "did:plc:b":
            raise KeyboardInterrupt
        return rows_for(did)

    monkeypatch.setattr(f"{MAIN}.load_repo", load_repo)
    queue = FakeQueue(events, [message("did:plc:a"), message("did:plc:b")])

    with pytest.raises(KeyboardInterrupt):
        run(FakeDidStore(events), queue, big_buffer(), "run-1")

    assert events[-1] == ("delete_many", ["handle-did:plc:a"])
