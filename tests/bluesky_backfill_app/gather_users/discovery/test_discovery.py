import pytest

from bluesky_backfill_app.gather_users.constants import FLUSH_REASON_FINAL
from bluesky_backfill_app.gather_users.discovery.main import discover, flush
from bluesky_backfill_app.gather_users.network.list_repos import RepoPage
from bluesky_backfill_app.gather_users.storage.buffer import DidBuffer
from bluesky_backfill_app.gather_users.storage.cursor import CursorTracker

DISCOVERY = "bluesky_backfill_app.gather_users.discovery.main"


class FakeCursorStore:
    def __init__(self, cursor=None, count=0):
        self.cursor = cursor
        self.count = count
        self.writes = []

    def read(self):
        return self.cursor, self.count

    def write(self, cursor, created_count):
        self.writes.append((cursor, created_count))


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
    store = FakeDidStore()

    flush(buffer, store, tracker, "run-1", FLUSH_REASON_FINAL)

    assert store.batches == [["did:plc:a"]]
    assert cursor_store.writes == [("next", 1)]
    assert len(buffer) == 0


def test_flush_is_a_noop_on_an_empty_buffer():
    cursor_store = FakeCursorStore()
    store = FakeDidStore()

    flush(DidBuffer(), store, CursorTracker(cursor_store), "run-1", FLUSH_REASON_FINAL)

    assert store.batches == []
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
    store = FakeDidStore()

    discover(store, tracker, "run-1", target=100)

    assert store.batches == [["did:plc:a", "did:plc:b", "did:plc:c"]]
    assert cursor_store.writes == [("one", 3)]
    assert tracker.discovered_count == 3


def test_discover_stops_once_the_target_is_reached(pages):
    pages.extend(
        [
            RepoPage(dids=["did:plc:a", "did:plc:b"], cursor="one"),
            RepoPage(dids=["did:plc:c"], cursor="two"),
        ]
    )
    tracker = CursorTracker(FakeCursorStore())
    store = FakeDidStore()

    discover(store, tracker, "run-1", target=2)

    assert store.batches == [["did:plc:a", "did:plc:b"]]
    assert tracker.discovered_count == 2


def test_discover_keeps_paging_when_duplicates_leave_it_short(pages):
    pages.extend(
        [
            RepoPage(dids=["did:plc:a", "did:plc:b"], cursor="one"),
            RepoPage(dids=["did:plc:c", "did:plc:d"], cursor="two"),
        ]
    )
    tracker = CursorTracker(FakeCursorStore())
    store = FakeDidStore(existing=["did:plc:a", "did:plc:b"])

    discover(store, tracker, "run-1", target=2)

    assert store.batches == [["did:plc:a", "did:plc:b"], ["did:plc:c", "did:plc:d"]]
    assert tracker.discovered_count == 2


def test_discover_resumes_from_the_stored_cursor(monkeypatch):
    seen = []

    def fake_iter_pages(cursor):
        seen.append(cursor)
        yield RepoPage(dids=["did:plc:a"], cursor=None)

    monkeypatch.setattr(f"{DISCOVERY}.iter_pages", fake_iter_pages)
    tracker = CursorTracker(FakeCursorStore(cursor="stored", count=5))

    discover(FakeDidStore(), tracker, "run-1", target=100)

    assert seen == ["stored"]


def test_discover_counts_the_existing_total_towards_the_target(pages):
    pages.append(RepoPage(dids=["did:plc:a"], cursor=None))
    tracker = CursorTracker(FakeCursorStore(cursor="stored", count=9))
    store = FakeDidStore()

    discover(store, tracker, "run-1", target=10)

    assert tracker.discovered_count == 10


def test_discover_does_not_write_when_already_at_target(pages):
    pages.append(RepoPage(dids=["did:plc:a"], cursor=None))
    cursor_store = FakeCursorStore(cursor="stored", count=10)
    store = FakeDidStore()

    discover(store, CursorTracker(cursor_store), "run-1", target=10)

    assert store.batches == []
    assert cursor_store.writes == []
