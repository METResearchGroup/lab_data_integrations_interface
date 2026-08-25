import pytest

from bluesky_backfill_app.gather_users.storage.cursor import CursorTracker


class FakeCursorStore:
    def __init__(self, cursor=None, count=0, fail_on_write=False):
        self.cursor = cursor
        self.count = count
        self.fail_on_write = fail_on_write
        self.writes = []

    def read(self):
        return self.cursor, self.count

    def write(self, cursor, created_count):
        if self.fail_on_write:
            raise RuntimeError("dynamo down")
        self.writes.append((cursor, created_count))


def test_reads_cursor_and_count_at_startup():
    tracker = CursorTracker(FakeCursorStore(cursor="abc", count=7))

    assert tracker.resume_from() == "abc"
    assert tracker.discovered_count == 7


def test_fresh_run_starts_at_the_beginning():
    tracker = CursorTracker(FakeCursorStore())

    assert tracker.resume_from() is None


def test_observe_does_not_advance_the_resume_point():
    store = FakeCursorStore(cursor="abc")
    tracker = CursorTracker(store)

    tracker.observe("def")

    assert tracker.resume_from() == "abc"
    assert store.writes == []


def test_mark_flushed_persists_and_advances():
    store = FakeCursorStore(cursor="abc", count=7)
    tracker = CursorTracker(store)

    tracker.observe("def")
    tracker.mark_flushed(3)

    assert store.writes == [("def", 3)]
    assert tracker.resume_from() == "def"
    assert tracker.discovered_count == 10


def test_observe_ignores_a_missing_cursor():
    store = FakeCursorStore(cursor="abc")
    tracker = CursorTracker(store)

    tracker.observe("def")
    tracker.observe(None)
    tracker.mark_flushed(1)

    assert store.writes == [("def", 1)]


def test_mark_flushed_is_a_noop_with_nothing_new():
    store = FakeCursorStore(cursor="abc", count=7)
    tracker = CursorTracker(store)

    tracker.mark_flushed(0)

    assert store.writes == []


def test_mark_flushed_writes_creations_at_an_unchanged_cursor():
    store = FakeCursorStore(cursor="abc", count=7)
    tracker = CursorTracker(store)

    tracker.mark_flushed(2)

    assert store.writes == [("abc", 2)]
    assert tracker.discovered_count == 9


def test_mark_flushed_skips_a_run_that_never_paged():
    store = FakeCursorStore()
    tracker = CursorTracker(store)

    tracker.mark_flushed(5)

    assert store.writes == []


def test_failed_write_leaves_the_cursor_and_count_untouched():
    store = FakeCursorStore(cursor="abc", count=7, fail_on_write=True)
    tracker = CursorTracker(store)
    tracker.observe("def")

    tracker.mark_flushed(3)

    assert tracker.resume_from() == "abc"
    assert tracker.discovered_count == 7


@pytest.mark.parametrize(
    ("count", "pending", "target", "expected"),
    [
        (7, 0, 10, False),
        (10, 0, 10, True),
        (11, 0, 10, True),
        (7, 3, 10, True),
        (7, 2, 10, False),
    ],
)
def test_target_reached(count, pending, target, expected):
    tracker = CursorTracker(FakeCursorStore(count=count))

    assert tracker.target_reached(target, pending) is expected
