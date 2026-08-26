from bluesky_backfill_app.aws.constants import STATUS_DISCOVERED, STATUS_QUEUED
from bluesky_backfill_app.gather_users.enqueue.main import drain, enqueue_pass


class FakeDidStore:
    """Holds DIDs by status and serves queries from a scripted set of pages."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.statuses = {}
        self.queries = []

    def query_by_status(self, status, limit):
        self.queries.append((status, limit))
        return self.pages.pop(0) if self.pages else []

    def set_status_many(self, dids, status):
        for did in dids:
            self.statuses[did] = status


class FakeQueue:
    def __init__(self, fail_dids=()):
        self.fail_dids = set(fail_dids)
        self.sent = []

    def send(self, dids, run_id):
        self.sent.extend(dids)
        return [did for did in dids if did in self.fail_dids]


def test_enqueue_pass_sends_and_marks():
    store = FakeDidStore([["did:plc:a", "did:plc:b"]])
    queue = FakeQueue()
    seen = set()

    found, sent = enqueue_pass(store, queue, "run-1", seen, page_size=10)

    assert (found, sent) == (2, 2)
    assert queue.sent == ["did:plc:a", "did:plc:b"]
    assert store.statuses == {"did:plc:a": STATUS_QUEUED, "did:plc:b": STATUS_QUEUED}
    assert seen == {"did:plc:a", "did:plc:b"}


def test_enqueue_pass_queries_the_discovered_status():
    store = FakeDidStore([[]])

    enqueue_pass(store, FakeQueue(), "run-1", set(), page_size=25)

    assert store.queries == [(STATUS_DISCOVERED, 25)]


def test_enqueue_pass_does_not_mark_a_failed_send():
    store = FakeDidStore([["did:plc:a", "did:plc:b"]])
    queue = FakeQueue(fail_dids=["did:plc:b"])
    seen = set()

    found, sent = enqueue_pass(store, queue, "run-1", seen, page_size=10)

    assert (found, sent) == (2, 1)
    assert store.statuses == {"did:plc:a": STATUS_QUEUED}
    assert seen == {"did:plc:a"}


def test_enqueue_pass_skips_dids_already_seen():
    store = FakeDidStore([["did:plc:a", "did:plc:b"]])
    queue = FakeQueue()

    found, sent = enqueue_pass(store, queue, "run-1", {"did:plc:a"}, page_size=10)

    assert (found, sent) == (2, 1)
    assert queue.sent == ["did:plc:b"]


def test_enqueue_pass_on_a_stale_page_sends_nothing():
    store = FakeDidStore([["did:plc:a"]])
    queue = FakeQueue()

    found, sent = enqueue_pass(store, queue, "run-1", {"did:plc:a"}, page_size=10)

    assert (found, sent) == (1, 0)
    assert queue.sent == []


def test_drain_runs_until_the_index_is_empty():
    store = FakeDidStore([["did:plc:a", "did:plc:b"], ["did:plc:c"], []])
    queue = FakeQueue()

    total = drain(store, queue, "run-1", page_size=10)

    assert total == 3
    assert queue.sent == ["did:plc:a", "did:plc:b", "did:plc:c"]


def test_drain_of_an_empty_index():
    store = FakeDidStore([[]])
    queue = FakeQueue()

    assert drain(store, queue, "run-1", page_size=10) == 0
    assert queue.sent == []


def test_drain_pages_through_a_lagging_index():
    """A stale page does not end the drain: real work behind it still goes out."""

    store = FakeDidStore([["did:plc:a"], ["did:plc:a"], ["did:plc:b"], []])
    queue = FakeQueue()

    total = drain(store, queue, "run-1", page_size=10)

    assert total == 2
    assert queue.sent == ["did:plc:a", "did:plc:b"]


def test_drain_does_not_resend_across_passes():
    store = FakeDidStore([["did:plc:a", "did:plc:b"], ["did:plc:b", "did:plc:c"], []])
    queue = FakeQueue()

    drain(store, queue, "run-1", page_size=10)

    assert queue.sent == ["did:plc:a", "did:plc:b", "did:plc:c"]
