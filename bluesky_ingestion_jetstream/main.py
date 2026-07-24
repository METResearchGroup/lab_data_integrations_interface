"""Entry point: stream from Jetstream, buffer, write to disk."""

import asyncio
from pathlib import Path

from bluesky_ingestion_jetstream.constants import DATA_DIR
from bluesky_ingestion_jetstream.network.connection import stream_events
from bluesky_ingestion_jetstream.storage.buffer import BufferSet, flush


async def run(data_dir: Path) -> None:
    """Consume the stream, buffering rows and writing them out when full."""

    buffers = BufferSet()

    async for record_type, row in stream_events():
        buffers.add(record_type, row)

        if buffers.should_flush():
            flush(buffers, data_dir)


def main() -> None:
    """CLI entry point."""

    asyncio.run(run(DATA_DIR))


if __name__ == "__main__":
    main()
