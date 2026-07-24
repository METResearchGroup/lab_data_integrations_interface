"""Jetstream WebSocket connection."""

from collections.abc import AsyncIterator


async def stream_events() -> AsyncIterator[str]:
    """Connect to Jetstream and yield raw messages."""

    # create websocket connection
    # for each event:
    # if commit, then process_commit_event()
    raise NotImplementedError


#    yield ""  # unreachable; makes this an async generator so `async for` type-checks


def process_commit_event(raw_message: str) -> tuple[str, dict] | None:
    """Turn a raw message into a (record_type, row) pair, or None if we don't store it."""
    print(raw_message)
    # parse_shared()
    # if post, parse_post() ... for all cases
