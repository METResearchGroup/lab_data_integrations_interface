"""Entry point: stream from Jetstream, buffer, commit to Iceberg."""

import asyncio
import logging
from uuid import uuid4

from bluesky_ingestion_jetstream.aws.catalog import build_catalog, load_tables
from bluesky_ingestion_jetstream.network.connection import stream_events
from bluesky_ingestion_jetstream.sinks.base import Sink
from bluesky_ingestion_jetstream.sinks.iceberg import IcebergSink
from bluesky_ingestion_jetstream.storage.buffer import BufferSet, flush

logger = logging.getLogger(__name__)


def new_run_id() -> str:
    """Identify one process lifetime, stamped onto every row it writes.

    A reconnect does not start a new run: the point of the column is to answer
    "which process produced this row", and `stream_events` reconnects
    transparently underneath a single `run()`.
    """

    return str(uuid4())


def build_sink(run_id: str) -> IcebergSink:
    """Load the four tables and wrap them in a sink.

    Done before the first event rather than at the first flush, so a catalog that
    is misconfigured fails in the first second. `load_tables` names every missing
    table at once, so a fresh environment gets one complete error instead of four
    consecutive ones.
    """

    return IcebergSink(load_tables(build_catalog()), run_id)


async def run(sink: Sink) -> None:
    """Consume the stream, buffering rows and committing them when full."""

    buffers = BufferSet()

    async for record_type, row in stream_events():
        buffers.add(record_type, row)

        if buffers.should_flush():
            flush(buffers, sink)


def main() -> None:
    """CLI entry point."""

    logging.basicConfig(level=logging.INFO)
    run_id = new_run_id()
    logger.info("starting ingestion run %s", run_id)
    asyncio.run(run(build_sink(run_id)))


if __name__ == "__main__":
    main()
