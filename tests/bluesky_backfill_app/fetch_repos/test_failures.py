import pytest

from bluesky_backfill_app.aws.constants import (
    MAX_RECEIVE_COUNT,
    REASON_ACCOUNT_DEACTIVATED,
    REASON_CAR_DECODE_ERROR,
    REASON_HTTP_5XX,
    REASON_LANDING_WRITE_ERROR,
    REASON_REPO_NOT_FOUND,
    REASON_SCHEMA_MISMATCH,
    REASON_UNKNOWN,
    STATUS_DEAD_LETTERED,
    STATUS_FAILED,
    STATUS_QUEUED,
)
from bluesky_backfill_app.aws.queue import Message
from bluesky_backfill_app.fetch_repos.failures import (
    RepoFailure,
    record_failure,
    record_flush_failure,
)
from bluesky_backfill_app.telemetry import instruments

ERROR = ValueError("boom")


class FakeCounter:
    def __init__(self):
        self.adds = []

    def add(self, amount, attributes=None):
        self.adds.append((amount, attributes))


@pytest.fixture(autouse=True)
def repos_failed(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(instruments, "repos_failed", counter)
    return counter


def counted(reason, did_status):
    return (1, {"reason": reason, "did_status": did_status})


class FakeDidStore:
    def __init__(self):
        self.failed = []

    def set_failed(self, did, status, error, reason):
        self.failed.append((did, status, reason, error))


class FakeQueue:
    def __init__(self):
        self.deleted = []

    def delete(self, handle):
        self.deleted.append(handle)


def message(did="did:plc:a", receive_count=1):
    return Message(did=did, run_id=None, handle=f"handle-{did}", receive_count=receive_count)


@pytest.mark.parametrize("reason", [REASON_ACCOUNT_DEACTIVATED, REASON_REPO_NOT_FOUND])
def test_a_permanent_failure_is_marked_failed_and_acked(reason, repos_failed):
    did_store, queue = FakeDidStore(), FakeQueue()

    record_failure(did_store, queue, message(), RepoFailure(reason, ERROR))

    assert did_store.failed == [("did:plc:a", STATUS_FAILED, reason, ERROR)]
    assert queue.deleted == ["handle-did:plc:a"]
    assert repos_failed.adds == [counted(reason, STATUS_FAILED)]


@pytest.mark.parametrize(
    "reason",
    [REASON_HTTP_5XX, REASON_UNKNOWN, REASON_CAR_DECODE_ERROR, REASON_SCHEMA_MISMATCH],
)
def test_any_other_failure_is_left_to_redeliver(reason, repos_failed):
    did_store, queue = FakeDidStore(), FakeQueue()

    record_failure(did_store, queue, message(), RepoFailure(reason, ERROR))

    assert did_store.failed == []
    assert queue.deleted == []
    assert repos_failed.adds == [counted(reason, STATUS_QUEUED)]


@pytest.mark.parametrize(
    "reason",
    [REASON_HTTP_5XX, REASON_UNKNOWN, REASON_CAR_DECODE_ERROR, REASON_SCHEMA_MISMATCH],
)
def test_any_other_failure_on_the_final_delivery_is_dead_lettered_without_an_ack(
    reason, repos_failed
):
    did_store, queue = FakeDidStore(), FakeQueue()

    record_failure(
        did_store, queue, message(receive_count=MAX_RECEIVE_COUNT), RepoFailure(reason, ERROR)
    )

    assert did_store.failed == [("did:plc:a", STATUS_DEAD_LETTERED, reason, ERROR)]
    assert queue.deleted == []
    assert repos_failed.adds == [counted(reason, STATUS_DEAD_LETTERED)]


def test_a_flush_failure_dead_letters_only_final_deliveries(repos_failed):
    did_store = FakeDidStore()
    messages = [message("did:plc:a"), message("did:plc:b", receive_count=MAX_RECEIVE_COUNT)]

    record_flush_failure(did_store, messages, ERROR)

    assert did_store.failed == [
        ("did:plc:b", STATUS_DEAD_LETTERED, REASON_LANDING_WRITE_ERROR, ERROR)
    ]
    assert repos_failed.adds == [
        counted(REASON_LANDING_WRITE_ERROR, STATUS_QUEUED),
        counted(REASON_LANDING_WRITE_ERROR, STATUS_DEAD_LETTERED),
    ]
