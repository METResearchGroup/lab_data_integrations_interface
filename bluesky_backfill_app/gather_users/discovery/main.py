"""Page listRepos, buffer DIDs, write them to DynamoDB, stop at target.

Run from repo root::

    PYTHONPATH=. uv run python -m bluesky_backfill_app.gather_users.discovery.main --count 1000
"""

import logging
from uuid import uuid4

import typer
from dotenv import load_dotenv

from bluesky_backfill_app.aws.did_store import DynamoDidStore
from bluesky_backfill_app.gather_users.constants import FLUSH_REASON_FINAL, FLUSH_REASON_TARGET
from bluesky_backfill_app.gather_users.cursor_store import DynamoCursorStore
from bluesky_backfill_app.gather_users.network.list_repos import iter_pages
from bluesky_backfill_app.gather_users.storage.buffer import DidBuffer
from bluesky_backfill_app.gather_users.storage.cursor import CursorTracker

logger = logging.getLogger(__name__)


def new_run_id() -> str:
    return str(uuid4())


def build_cursor_tracker() -> CursorTracker:
    return CursorTracker(DynamoCursorStore())


def flush(
    buffer: DidBuffer,
    did_store: DynamoDidStore,
    tracker: CursorTracker,
    run_id: str,
    reason: str,
) -> int:
    """Write the buffer, then advance the cursor. Never the reverse. Returns DIDs created."""

    if not buffer.dids:
        return 0

    buffered = len(buffer)
    created = did_store.write(buffer.dids, run_id)
    buffer.clear()
    tracker.mark_flushed()

    logger.info("flushed %d dids (%s), %d created", buffered, reason, created)
    return created


def discover(did_store: DynamoDidStore, tracker: CursorTracker, run_id: str, count: int) -> int:
    """Page from the stored cursor until `count` new DIDs exist, flushing on thresholds.

    DIDs already in the table do not count, so paging continues until `count`
    are actually new. Returns the number created.
    """

    created = 0
    if count <= 0:
        return created

    buffer = DidBuffer()

    for page in iter_pages(tracker.resume_from()):
        for did in page.dids:
            buffer.add(did)
        tracker.observe(page.cursor)

        if buffer.should_flush():
            created += flush(buffer, did_store, tracker, run_id, buffer.flush_reason())
        elif created + len(buffer) >= count:
            created += flush(buffer, did_store, tracker, run_id, FLUSH_REASON_TARGET)

        if created >= count:
            return created

    return created + flush(buffer, did_store, tracker, run_id, FLUSH_REASON_FINAL)


def main(
    count: int = typer.Option(..., min=1, help="Number of new DIDs to add before exiting"),
):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load_dotenv()

    tracker = build_cursor_tracker()
    logger.info("resuming from %s", tracker.resume_from())
    created = discover(DynamoDidStore(), tracker, new_run_id(), count)
    logger.info("added %d dids", created)


if __name__ == "__main__":
    typer.run(main)
