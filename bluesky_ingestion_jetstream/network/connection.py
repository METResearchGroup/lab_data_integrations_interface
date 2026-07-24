"""Jetstream WebSocket connection."""

from collections.abc import AsyncIterator


async def stream_events() -> AsyncIterator[str]:
    """Connect to Jetstream and yield raw messages."""

    # create websocket connection
    # for each event:
    # if commit, then process_commit_event()
    raise NotImplementedError


def process_commit_event(raw_message: str) -> dict | None:
    """Turn a raw message into a row, or None if we don't store it."""
    print(raw_message)
    # parse_shared()
    # if post, parse_post() ... for all cases
