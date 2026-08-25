"""Page listRepos, buffer DIDs, write them to DynamoDB, stop at target.

Run from repo root::

    PYTHONPATH=. uv run python -m bluesky_backfill_app.discovery.main --target 1000000
"""

import logging
from uuid import uuid4

import typer
from dotenv import load_dotenv

from bluesky_backfill_app.aws.cursor_store import DynamoCursorStore
from bluesky_backfill_app.aws.did_store import DynamoDidStore
from bluesky_backfill_app.constants import FLUSH_REASON_FINAL, FLUSH_REASON_TARGET
from bluesky_backfill_app.network.list_repos import iter_pages
from bluesky_backfill_app.storage.buffer import DidBuffer
from bluesky_backfill_app.storage.cursor import CursorTracker

logger = logging.getLogger(__name__)


def new_run_id() -> str:
    return str(uuid4())


def build_cursor_tracker() -> CursorTracker:
    return CursorTracker(DynamoCursorStore())


def flush(
    buffer: DidBuffer,
    store: DynamoDidStore,
    tracker: CursorTracker,
    run_id: str,
    reason: str,
) -> None:
    """Write the buffer, then advance the cursor. Never the reverse."""

    if not buffer.dids:
        return

    buffered = len(buffer)
    created = store.write(buffer.dids, run_id)
    buffer.clear()
    tracker.mark_flushed(created)

    logger.info(
        "flushed %d dids (%s), %d created, %d total",
        buffered,
        reason,
        created,
        tracker.discovered_count,
    )


def discover(store: DynamoDidStore, tracker: CursorTracker, run_id: str, target: int) -> None:
    """Page from the stored cursor until `target` DIDs exist, flushing on thresholds.

    The target check runs against the persisted count, so DIDs already in the
    table do not count towards it and paging continues until the count is real.
    """

    if tracker.target_reached(target):
        return

    buffer = DidBuffer()

    for page in iter_pages(tracker.resume_from()):
        for did in page.dids:
            buffer.add(did)
        tracker.observe(page.cursor)

        if buffer.should_flush():
            flush(buffer, store, tracker, run_id, buffer.flush_reason())
        elif tracker.target_reached(target, len(buffer)):
            flush(buffer, store, tracker, run_id, FLUSH_REASON_TARGET)

        if tracker.target_reached(target):
            return

    flush(buffer, store, tracker, run_id, FLUSH_REASON_FINAL)


def main(
    target: int = typer.Option(..., help="Number of DIDs to collect before exiting"),
):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load_dotenv()

    tracker = build_cursor_tracker()
    logger.info("resuming from %s with %d dids", tracker.resume_from(), tracker.discovered_count)
    discover(DynamoDidStore(), tracker, new_run_id(), target)


if __name__ == "__main__":
    typer.run(main)
