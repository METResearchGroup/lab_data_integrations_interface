"""Entry point: stream from Jetstream, buffer, commit to Iceberg."""

import asyncio
import logging
from contextlib import suppress
from uuid import uuid4

from bluesky_ingestion_jetstream.aws.catalog import build_catalog, load_tables
from bluesky_ingestion_jetstream.aws.cursor_store import DynamoCursorStore
from bluesky_ingestion_jetstream.constants import FLUSH_CHECK_INTERVAL_SECONDS
from bluesky_ingestion_jetstream.network.connection import stream_events
from bluesky_ingestion_jetstream.sinks.base import Sink
from bluesky_ingestion_jetstream.sinks.iceberg import IcebergSink
from bluesky_ingestion_jetstream.storage.buffer import BufferSet, flush
from bluesky_ingestion_jetstream.storage.cursor import CursorTracker

logger = logging.getLogger(__name__)


def new_run_id() -> str:
    return str(uuid4())


def build_sink(run_id: str) -> IcebergSink:
    return IcebergSink(load_tables(build_catalog()), run_id)


def build_tracker() -> CursorTracker:
    return CursorTracker(DynamoCursorStore())


async def flush_loop(
    buffers: BufferSet, sink: Sink, tracker: CursorTracker, interval: float
) -> None:
    """Flush on a timer, so the age threshold fires even with no events arriving."""

    while True:
        await asyncio.sleep(interval)
        # Neither call awaits, so the read loop cannot add to a buffer between
        # the write and the cursor advancing past it.
        if buffers.should_flush():
            flush(buffers, sink)
            tracker.mark_flushed()


async def run(
    sink: Sink, tracker: CursorTracker, flush_interval: float = FLUSH_CHECK_INTERVAL_SECONDS
) -> None:
    """Consume the stream into the buffers while `flush_loop` drains them."""

    buffers = BufferSet()
    flusher = asyncio.create_task(flush_loop(buffers, sink, tracker, flush_interval))

    try:
        async for event in stream_events(tracker.resume_from):
            # Nothing is draining the buffers if it died; they would grow unbounded.
            if flusher.done():
                flusher.result()

            tracker.observe(event.time_us)
            if event.parsed is not None:
                buffers.add(*event.parsed)
    finally:
        flusher.cancel()
        # Re-raises a failure, so a flush that broke on the last event still surfaces.
        with suppress(asyncio.CancelledError):
            await flusher


def main() -> None:
    """CLI entry point."""

    logging.basicConfig(level=logging.INFO)
    run_id = new_run_id()
    logger.info("starting ingestion run %s", run_id)
    tracker = build_tracker()
    logger.info("resuming from cursor %s", tracker.resume_from())
    asyncio.run(run(build_sink(run_id), tracker))


if __name__ == "__main__":
    main()
