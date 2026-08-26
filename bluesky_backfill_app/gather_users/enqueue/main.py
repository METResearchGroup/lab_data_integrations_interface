"""Send discovered DIDs to SQS and mark them queued.

Run from repo root::

    PYTHONPATH=. uv run python -m bluesky_backfill_app.gather_users.enqueue.main
"""

import logging
import time
from uuid import uuid4

import typer
from dotenv import load_dotenv

from bluesky_backfill_app.aws.constants import STATUS_DISCOVERED, STATUS_QUEUED
from bluesky_backfill_app.aws.did_store import DynamoDidStore
from bluesky_backfill_app.aws.queue import SqsQueue
from bluesky_backfill_app.gather_users.constants import ENQUEUE_PAGE_SIZE

logger = logging.getLogger(__name__)


def new_run_id() -> str:
    return str(uuid4())


def enqueue_pass(
    store: DynamoDidStore,
    queue: SqsQueue,
    run_id: str,
    seen: set[str],
    page_size: int,
) -> tuple[int, int]:
    """One query-send-mark cycle. Returns (DIDs found, DIDs sent).

    Sends before marking, so a crash re-sends rather than drops.
    """

    found = store.query_by_status(STATUS_DISCOVERED, page_size)
    fresh = [did for did in found if did not in seen]
    if not fresh:
        return len(found), 0

    failed = set(queue.send(fresh, run_id))
    sent = [did for did in fresh if did not in failed]

    store.set_status_many(sent, STATUS_QUEUED)
    seen.update(sent)
    return len(found), len(sent)


def drain(
    store: DynamoDidStore,
    queue: SqsQueue,
    run_id: str,
    page_size: int = ENQUEUE_PAGE_SIZE,
) -> int:
    """Enqueue until the status index runs dry. Returns the number sent.

    A pass that finds only DIDs already sent this run just goes round again;
    `status_index` is a GSI and lags writes.
    """

    seen: set[str] = set()
    total = 0

    while True:
        found, sent = enqueue_pass(store, queue, run_id, seen, page_size)
        if found == 0:
            return total

        total += sent
        if sent:
            logger.info("sent %d dids, %d this run", sent, total)


def main(
    poll_seconds: float = typer.Option(
        0.0, help="Seconds between drains. 0 drains once and exits"
    ),
):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load_dotenv()

    store = DynamoDidStore()
    queue = SqsQueue()

    while True:
        drain(store, queue, new_run_id())
        if poll_seconds <= 0:
            return
        time.sleep(poll_seconds)


if __name__ == "__main__":
    typer.run(main)
