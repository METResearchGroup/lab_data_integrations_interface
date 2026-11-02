from bluesky_backfill_app.gather_users.storage.cursor import CursorTracker


class FakeCursorStore:
    def __init__(self, cursor=None, fail_on_write=False):
        self.cursor = cursor
        self.fail_on_write = fail_on_write
        self.writes = []

    def read(self):
        return self.cursor

    def write(self, cursor):
        if self.fail_on_write:
            raise RuntimeError("dynamo down")
        self.writes.append(cursor)


def test_reads_the_cursor_at_startup():
    tracker = CursorTracker(FakeCursorStore(cursor="abc"))

    assert tracker.resume_from() == "abc"


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
    store = FakeCursorStore(cursor="abc")
    tracker = CursorTracker(store)

    tracker.observe("def")
    tracker.mark_flushed()

    assert store.writes == ["def"]
    assert tracker.resume_from() == "def"


def test_observe_ignores_a_missing_cursor():
    store = FakeCursorStore(cursor="abc")
    tracker = CursorTracker(store)

    tracker.observe("def")
    tracker.observe(None)
    tracker.mark_flushed()

    assert store.writes == ["def"]


def test_mark_flushed_is_a_noop_at_an_unchanged_cursor():
    store = FakeCursorStore(cursor="abc")
    tracker = CursorTracker(store)

    tracker.observe("abc")
    tracker.mark_flushed()

    assert store.writes == []


def test_mark_flushed_skips_a_run_that_never_paged():
    store = FakeCursorStore()
    tracker = CursorTracker(store)

    tracker.mark_flushed()

    assert store.writes == []


def test_failed_write_leaves_the_cursor_untouched():
    store = FakeCursorStore(cursor="abc", fail_on_write=True)
    tracker = CursorTracker(store)
    tracker.observe("def")

    tracker.mark_flushed()

    assert tracker.resume_from() == "abc"
