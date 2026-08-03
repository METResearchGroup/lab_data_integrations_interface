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
    return str(uuid4())


def build_sink(run_id: str) -> IcebergSink:
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
