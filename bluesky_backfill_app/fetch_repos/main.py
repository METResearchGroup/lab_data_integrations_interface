"""Fetch queued repos, land them as Parquet, mark them done.

Run from repo root::

    PYTHONPATH=. uv run python -m bluesky_backfill_app.fetch_repos.main
"""

import logging
import signal
import time
from uuid import uuid4

import typer
from dotenv import load_dotenv

from bluesky_backfill_app.aws.constants import STATUS_DONE
from bluesky_backfill_app.aws.did_store import DynamoDidStore
from bluesky_backfill_app.aws.queue import Message, SqsQueue
from bluesky_backfill_app.fetch_repos.constants import FLUSH_REASON_STOP
from bluesky_backfill_app.fetch_repos.failures import (
    RepoFailure,
    record_failure,
    record_flush_failure,
)
from bluesky_backfill_app.fetch_repos.landing.writer import write_buffer
from bluesky_backfill_app.fetch_repos.repo import load_repo
from bluesky_backfill_app.fetch_repos.storage.buffer import RepoBuffer

logger = logging.getLogger(__name__)


def new_run_id() -> str:
    return str(uuid4())


def process_message(
    message: Message,
    did_store: DynamoDidStore,
    queue: SqsQueue,
    buffer: RepoBuffer,
    received_at: float,
) -> None:
    try:
        rows = load_repo(message.did)
    except RepoFailure as failure:
        record_failure(did_store, queue, message, failure)
        return
    buffer.add(message, rows, received_at)


def flush(
    buffer: RepoBuffer,
    did_store: DynamoDidStore,
    queue: SqsQueue,
    run_id: str,
    reason: str,
) -> None:
    """S3, then DynamoDB, then ack. The buffer is cleared either way."""

    messages = buffer.messages
    try:
        paths = write_buffer(buffer, run_id)
        did_store.set_status_many([message.did for message in messages], STATUS_DONE)
    except Exception as error:
        logger.exception("flush of %d dids failed", len(messages))
        record_flush_failure(did_store, messages, error)
        return
    finally:
        buffer.clear()

    queue.delete_many([message.handle for message in messages])
    logger.info("flushed %d dids (%s) to %d files", len(messages), reason, len(paths))


def run(did_store: DynamoDidStore, queue: SqsQueue, buffer: RepoBuffer, run_id: str) -> None:
    try:
        while True:
            message = queue.receive()
            if message is not None:
                process_message(message, did_store, queue, buffer, time.monotonic())
            if buffer.should_flush():
                flush(buffer, did_store, queue, run_id, buffer.flush_reason())
    finally:
        if buffer.messages:
            flush(buffer, did_store, queue, run_id, FLUSH_REASON_STOP)


def sigterm_handler(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load_dotenv()
    signal.signal(signal.SIGTERM, sigterm_handler)

    run_id = new_run_id()
    logger.info("starting fetch run %s", run_id)
    try:
        run(DynamoDidStore(), SqsQueue(), RepoBuffer(), run_id)
    except KeyboardInterrupt:
        logger.info("stopped")


if __name__ == "__main__":
    typer.run(main)
