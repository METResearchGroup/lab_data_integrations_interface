"""Entry point: stream from Jetstream, buffer, write to disk."""

import asyncio
from pathlib import Path
from uuid import uuid4

from bluesky_ingestion_jetstream.constants import DATA_DIR
from bluesky_ingestion_jetstream.network.connection import stream_events
from bluesky_ingestion_jetstream.storage.buffer import BufferSet, flush


def new_run_id() -> str:
    """Identify one process lifetime, stamped onto every row it writes.

    A reconnect does not start a new run: the point of the column is to answer
    "which process produced this row", and `stream_events` reconnects
    transparently underneath a single `run()`.
    """

    return str(uuid4())


async def run(data_dir: Path, run_id: str) -> None:
    """Consume the stream, buffering rows and writing them out when full."""

    buffers = BufferSet()

    async for record_type, row in stream_events():
        buffers.add(record_type, row)

        if buffers.should_flush():
            flush(buffers, data_dir, run_id)


def main() -> None:
    """CLI entry point."""

    asyncio.run(run(DATA_DIR, new_run_id()))


if __name__ == "__main__":
    main()
