import json

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
from bluesky_backfill_app.fetch_repos.constants import SIGTERM_EXIT_CODE
from bluesky_backfill_app.fetch_repos.failures import RepoFailure
from bluesky_backfill_app.fetch_repos.landing.writer import build_table
from bluesky_backfill_app.fetch_repos.main import flush, main, process_message, run
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

    def __init__(self, events, messages=(), waiting=(0,), in_flight=(0,)):
        self.events = events
        self.messages = list(messages)
        self.waiting = list(waiting)
        self.in_flight = list(in_flight)

    def receive(self):
        if not self.messages:
            raise KeyboardInterrupt
        return self.messages.pop(0)

    def waiting_messages(self):
        return self.waiting.pop(0)

    def in_flight_messages(self):
        return self.in_flight.pop(0)

    def delete(self, handle):
        self.events.append(("delete", handle))

    def delete_many(self, handles):
        self.events.append(("delete_many", handles))
        return []


def message(did, receive_count=1):
    return Message(did=did, run_id=None, handle=f"handle-{did}", receive_count=receive_count)


def tables_for(did, run_id="run-1"):
    return {LIKES: build_table(LIKES, [{"uri": f"at://{did}/app.bsky.feed.like/1", "did": did}])}


def big_buffer():
    return RepoBuffer(max_size_bytes=10**12, max_age_seconds=10**9)


@pytest.fixture
def events(monkeypatch):
    events = []

    def write_buffer(buffer, run_id):
        events.append(("write", [m.did for m in buffer.messages]))
        return ["path"]

    monkeypatch.setattr(f"{MAIN}.write_buffer", write_buffer)
    monkeypatch.setattr(f"{MAIN}.load_repo", tables_for)
    return events


def test_process_message_buffers_a_loaded_repo(events):
    buffer = big_buffer()

    process_message(
        message("did:plc:a"), FakeDidStore(events), FakeQueue(events), buffer, "run-1", 0.0
    )

    assert [m.did for m in buffer.messages] == ["did:plc:a"]
    assert len(buffer.tables[LIKES]) == 1
    assert events == []


def test_process_message_records_a_failure_instead_of_buffering(events, monkeypatch):
    def load_repo(did, run_id):
        raise RepoFailure(REASON_ACCOUNT_TAKENDOWN, ValueError())

    monkeypatch.setattr(f"{MAIN}.load_repo", load_repo)
    buffer = big_buffer()

    process_message(
        message("did:plc:a"), FakeDidStore(events), FakeQueue(events), buffer, "run-1", 0.0
    )

    assert buffer.messages == []
    assert events == [
        ("set_failed", "did:plc:a", STATUS_FAILED, REASON_ACCOUNT_TAKENDOWN),
        ("delete", "handle-did:plc:a"),
    ]


def fill(buffer, *messages):
    for msg in messages:
        buffer.add(msg, tables_for(msg.did), 0.0)


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


def flush_lines(caplog):
    return [json.loads(m) for m in caplog.messages if m.startswith('{"event": "flush"')]


def test_flush_logs_what_it_landed(events, caplog):
    buffer = big_buffer()
    fill(buffer, message("did:plc:a"), message("did:plc:b"))

    with caplog.at_level("INFO"):
        flush(buffer, FakeDidStore(events), FakeQueue(events), "run-1", "size")

    [line] = flush_lines(caplog)
    assert (line["status"], line["reason"], line["repos"], line["likes_rows"]) == (
        "ok",
        "size",
        2,
        2,
    )


def test_a_failed_flush_still_logs_what_it_held(events, caplog):
    buffer = big_buffer()
    fill(buffer, message("did:plc:a"))

    with caplog.at_level("INFO"):
        flush(buffer, FakeDidStore(events, fail_done=True), FakeQueue(events), "run-1", "age")

    [line] = flush_lines(caplog)
    assert (line["status"], line["repos"], line["likes_rows"]) == ("failed", 1, 1)


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
    def load_repo(did, run_id):
        if did == "did:plc:b":
            raise KeyboardInterrupt
        return tables_for(did)

    monkeypatch.setattr(f"{MAIN}.load_repo", load_repo)
    queue = FakeQueue(events, [message("did:plc:a"), message("did:plc:b")])

    with pytest.raises(KeyboardInterrupt):
        run(FakeDidStore(events), queue, big_buffer(), "run-1")

    assert events[-1] == ("delete_many", ["handle-did:plc:a"])


def test_run_keeps_polling_before_the_idle_limit(events):
    queue = FakeQueue(events, [None])

    with pytest.raises(KeyboardInterrupt):
        run(FakeDidStore(events), queue, big_buffer(), "run-1")


def test_run_flushes_and_returns_once_idle_and_drained(events, monkeypatch):
    monkeypatch.setattr(f"{MAIN}.IDLE_EXIT_SECONDS", 0)
    queue = FakeQueue(events, [message("did:plc:a"), None])

    run(FakeDidStore(events), queue, big_buffer(), "run-1")

    assert events[-1] == ("delete_many", ["handle-did:plc:a"])


@pytest.mark.parametrize(
    ("waiting", "in_flight"),
    [((1, 0), (0,)), ((0, 0), (1, 0))],
)
def test_run_waits_for_messages_the_queue_still_holds(events, monkeypatch, waiting, in_flight):
    monkeypatch.setattr(f"{MAIN}.IDLE_EXIT_SECONDS", 0)
    queue = FakeQueue(events, [None, None], waiting=waiting, in_flight=in_flight)

    run(FakeDidStore(events), queue, big_buffer(), "run-1")

    assert queue.messages == []


@pytest.fixture
def main_dependencies(monkeypatch):
    for name in (
        "load_dotenv",
        "fill_unset_secrets",
        "setup_telemetry",
        "signal.signal",
        "SqsQueue",
        "DynamoDidStore",
        "register_buffer",
        "register_queues",
        "force_telemetry_flush",
    ):
        monkeypatch.setattr(f"{MAIN}.{name}", lambda *args, **kwargs: None)


def test_main_exits_nonzero_when_stopped(main_dependencies, monkeypatch):
    def stopped(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(f"{MAIN}.run", stopped)

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == SIGTERM_EXIT_CODE


def test_main_returns_when_the_queue_drains(main_dependencies, monkeypatch):
    monkeypatch.setattr(f"{MAIN}.run", lambda *args: None)

    main()
