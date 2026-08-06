"""Entry point: stream from Jetstream, buffer, commit to Iceberg."""

import asyncio
import logging
import signal
from contextlib import suppress
from uuid import uuid4

from bluesky_ingestion_jetstream.aws.catalog import build_catalog, load_tables
from bluesky_ingestion_jetstream.aws.cursor_store import DynamoCursorStore
from bluesky_ingestion_jetstream.constants import FLUSH_CHECK_INTERVAL_SECONDS
from bluesky_ingestion_jetstream.network.connection import stream_events
from bluesky_ingestion_jetstream.sinks.base import Sink
from bluesky_ingestion_jetstream.sinks.iceberg import IcebergSink
from bluesky_ingestion_jetstream.storage.buffer import BufferSet, flush, get_flush_summary
from bluesky_ingestion_jetstream.storage.cursor import CursorTracker
from bluesky_ingestion_jetstream.telemetry import (
    force_telemetry_flush,
    record_flush,
    setup_telemetry,
)

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
            summary = get_flush_summary(buffers, buffers.flush_reason())
            flush(buffers, sink)
            tracker.mark_flushed()
            record_flush(summary)


async def consume_stream(
    sink: Sink, tracker: CursorTracker, flush_interval: float = FLUSH_CHECK_INTERVAL_SECONDS
) -> None:
    """Fill the buffers from the stream while `flush_loop` drains them."""

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


async def start_run(flush_interval: float = FLUSH_CHECK_INTERVAL_SECONDS) -> None:
    """Build the real collaborators and consume until something stops us."""

    run_id = new_run_id()
    logger.info("starting ingestion run %s", run_id)

    try:
        tracker = build_tracker()
        sink = build_sink(run_id)
    except Exception:
        logger.exception("could not start run %s; check the Glue tables and DynamoDB", run_id)
        raise

    logger.info("resuming from cursor %s", tracker.resume_from())

    try:
        await consume_stream(sink, tracker, flush_interval)
    except Exception:
        logger.exception("ingestion run %s died", run_id)
        raise


def sigterm_handler(_signum: int, _frame: object) -> None:
    """Convert SIGTERM into a KeyboardInterrupt exception."""

    raise KeyboardInterrupt


def run_until_stopped() -> None:
    """Run the pipeline until stopped, guaranteeing a final telemetry flush on shutdown."""

    signal.signal(signal.SIGTERM, sigterm_handler)

    try:
        asyncio.run(start_run())
    except KeyboardInterrupt:
        # A stop asked for by an operator or a supervisor, so not a failure.
        logger.info("stopped")
    finally:
        force_telemetry_flush()


def main() -> None:
    """CLI entry point."""

    logging.basicConfig(level=logging.INFO)
    setup_telemetry()
    run_until_stopped()


if __name__ == "__main__":
    main()
