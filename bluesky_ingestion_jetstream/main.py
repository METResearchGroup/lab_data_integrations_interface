"""Entry point: stream from Jetstream, buffer, commit to Iceberg."""

import asyncio
import logging
from uuid import uuid4

from bluesky_ingestion_jetstream.aws.catalog import build_catalog, load_tables
from bluesky_ingestion_jetstream.aws.cursor_store import DynamoCursorStore
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


def build_tracker(run_id: str) -> CursorTracker:
    return CursorTracker(DynamoCursorStore(run_id))


async def run(sink: Sink, tracker: CursorTracker) -> None:
    """Consume the stream, buffering rows and committing them when full.

    The cursor advances only after `flush` returns, so it is never ahead of an
    event that is not yet written.
    """

    buffers = BufferSet()

    async for event in stream_events(tracker.resume_from):
        tracker.observe(event.time_us)
        if event.parsed is not None:
            buffers.add(*event.parsed)

        if buffers.should_flush():
            flush(buffers, sink)
            tracker.mark_flushed()


def main() -> None:
    """CLI entry point."""

    logging.basicConfig(level=logging.INFO)
    run_id = new_run_id()
    logger.info("starting ingestion run %s", run_id)
    tracker = build_tracker(run_id)
    logger.info("resuming from cursor %s", tracker.resume_from())
    asyncio.run(run(build_sink(run_id), tracker))


if __name__ == "__main__":
    main()
