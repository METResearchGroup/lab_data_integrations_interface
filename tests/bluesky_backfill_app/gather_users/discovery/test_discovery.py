import pytest

from bluesky_backfill_app.gather_users.constants import FLUSH_REASON_FINAL
from bluesky_backfill_app.gather_users.discovery.main import discover, flush
from bluesky_backfill_app.gather_users.network.list_repos import RepoPage
from bluesky_backfill_app.gather_users.storage.buffer import DidBuffer
from bluesky_backfill_app.gather_users.storage.cursor import CursorTracker

DISCOVERY = "bluesky_backfill_app.gather_users.discovery.main"


class FakeCursorStore:
    def __init__(self, cursor=None):
        self.cursor = cursor
        self.writes = []

    def read(self):
        return self.cursor

    def write(self, cursor):
        self.writes.append(cursor)


class FakeDidStore:
    """Records write order and treats `existing` DIDs as already present."""

    def __init__(self, existing=()):
        self.existing = set(existing)
        self.batches = []

    def write(self, dids, run_id):
        self.batches.append(list(dids))
        created = [did for did in dids if did not in self.existing]
        self.existing.update(created)
        return len(created)


@pytest.fixture
def pages(monkeypatch):
    """Patches iter_pages; append RepoPages to the returned list."""

    supplied: list[RepoPage] = []

    def fake_iter_pages(cursor):
        yield from supplied

    monkeypatch.setattr(f"{DISCOVERY}.iter_pages", fake_iter_pages)
    return supplied


def test_flush_writes_then_advances_the_cursor():
    buffer = DidBuffer()
    buffer.add("did:plc:a")
    cursor_store = FakeCursorStore()
    tracker = CursorTracker(cursor_store)
    tracker.observe("next")
    did_store = FakeDidStore()

    created = flush(buffer, did_store, tracker, "run-1", FLUSH_REASON_FINAL)

    assert created == 1
    assert did_store.batches == [["did:plc:a"]]
    assert cursor_store.writes == ["next"]
    assert len(buffer) == 0


def test_flush_is_a_noop_on_an_empty_buffer():
    cursor_store = FakeCursorStore()
    did_store = FakeDidStore()

    flush(DidBuffer(), did_store, CursorTracker(cursor_store), "run-1", FLUSH_REASON_FINAL)

    assert did_store.batches == []
    assert cursor_store.writes == []


def test_discover_writes_every_page_and_stops_at_the_end(pages):
    pages.extend(
        [
            RepoPage(dids=["did:plc:a", "did:plc:b"], cursor="one"),
            RepoPage(dids=["did:plc:c"], cursor=None),
        ]
    )
    cursor_store = FakeCursorStore()
    tracker = CursorTracker(cursor_store)
    did_store = FakeDidStore()

    created = discover(did_store, tracker, "run-1", count=100)

    assert created == 3
    assert did_store.batches == [["did:plc:a", "did:plc:b", "did:plc:c"]]
    assert cursor_store.writes == ["one"]


def test_discover_stops_once_count_is_reached(pages):
    pages.extend(
        [
            RepoPage(dids=["did:plc:a", "did:plc:b"], cursor="one"),
            RepoPage(dids=["did:plc:c"], cursor="two"),
        ]
    )
    tracker = CursorTracker(FakeCursorStore())
    did_store = FakeDidStore()

    created = discover(did_store, tracker, "run-1", count=2)

    assert created == 2
    assert did_store.batches == [["did:plc:a", "did:plc:b"]]


def test_discover_keeps_paging_when_duplicates_leave_it_short(pages):
    pages.extend(
        [
            RepoPage(dids=["did:plc:a", "did:plc:b"], cursor="one"),
            RepoPage(dids=["did:plc:c", "did:plc:d"], cursor="two"),
        ]
    )
    tracker = CursorTracker(FakeCursorStore())
    did_store = FakeDidStore(existing=["did:plc:a", "did:plc:b"])

    created = discover(did_store, tracker, "run-1", count=2)

    assert created == 2
    assert did_store.batches == [["did:plc:a", "did:plc:b"], ["did:plc:c", "did:plc:d"]]


def test_discover_resumes_from_the_stored_cursor(monkeypatch):
    seen = []

    def fake_iter_pages(cursor):
        seen.append(cursor)
        yield RepoPage(dids=["did:plc:a"], cursor=None)

    monkeypatch.setattr(f"{DISCOVERY}.iter_pages", fake_iter_pages)
    tracker = CursorTracker(FakeCursorStore(cursor="stored"))

    discover(FakeDidStore(), tracker, "run-1", count=100)

    assert seen == ["stored"]


def test_discover_does_not_write_when_count_is_zero(pages):
    pages.append(RepoPage(dids=["did:plc:a"], cursor=None))
    cursor_store = FakeCursorStore(cursor="stored")
    did_store = FakeDidStore()

    created = discover(did_store, CursorTracker(cursor_store), "run-1", count=0)

    assert created == 0
    assert did_store.batches == []
    assert cursor_store.writes == []
