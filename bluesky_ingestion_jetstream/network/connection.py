"""Jetstream WebSocket connection."""

import asyncio
import json
from collections.abc import AsyncIterable, AsyncIterator
from urllib.parse import urlencode

import websockets
from websockets.exceptions import WebSocketException

from bluesky_ingestion_jetstream.constants import (
    BACKOFF_MULTIPLIER,
    COLLECTION_TO_RECORD_TYPE,
    FOLLOWS,
    INITIAL_BACKOFF_SECONDS,
    JETSTREAM_ENDPOINT,
    LIKES,
    MAX_BACKOFF_SECONDS,
    POSTS,
    REPOSTS,
    REQUIRED_KEYS,
    WANTED_COLLECTIONS,
)
from bluesky_ingestion_jetstream.event_parsing.follows import parse_follow
from bluesky_ingestion_jetstream.event_parsing.likes_and_reposts import parse_like_or_repost
from bluesky_ingestion_jetstream.event_parsing.posts import parse_post
from bluesky_ingestion_jetstream.event_parsing.shared import (
    as_dict,
    as_str,
    parse_shared,
    validate_non_null_fields,
)


def build_url() -> str:
    """The subscribe URL, filtered server-side to the collections we store."""

    params = [("wantedCollections", collection) for collection in WANTED_COLLECTIONS]
    return f"{JETSTREAM_ENDPOINT}?{urlencode(params)}"


def is_commit(event: object) -> bool:
    """Whether this event is a commit. Identity and account events are not."""

    return isinstance(event, dict) and event.get("kind") == "commit"


async def process_all_websocket_events(
    messages: AsyncIterable[str | bytes],
) -> AsyncIterator[tuple[str, dict]]:
    """Yield (record_type, row) pairs for the commits in a stream of raw messages.

    Takes any async iterable rather than a socket, so it can be exercised with a
    plain list of messages.
    """

    async for message in messages:
        # Frames arrive as raw text, so this is the one place we deserialize.
        try:
            event = json.loads(message)
        except json.JSONDecodeError:
            continue

        # only want posts/reposts/likes/follows
        if not is_commit(event):
            continue

        # off-chance that data has a null field
        parsed = process_commit_event(event)
        if parsed is not None:
            yield parsed


def process_commit_event(event: dict) -> tuple[str, dict] | None:
    """Turn a commit into a (record_type, row) pair, or None if we don't store it.

    The caller has already established that this is a commit.
    """

    commit = as_dict(event.get("commit"))
    # Anything but a create is an edit or the deleted-post case.
    if commit.get("operation") != "create":
        return None

    collection = as_str(commit.get("collection"))
    record_type = COLLECTION_TO_RECORD_TYPE.get(collection) if collection else None
    record = as_dict(commit.get("record"))
    row = parse_shared(event)

    if record_type == POSTS:
        row |= parse_post(record)
    elif record_type == FOLLOWS:
        row |= parse_follow(record)
    elif record_type in (LIKES, REPOSTS):
        row |= parse_like_or_repost(record)
    else:
        return None

    if not validate_non_null_fields(row, REQUIRED_KEYS[record_type]):
        return None
    return record_type, row


async def stream_events() -> AsyncIterator[tuple[str, dict]]:
    """Connect to Jetstream and yield (record_type, row) pairs for commits.

    Reconnects with exponential backoff. The backoff resets only once a row has
    actually come through, not merely on a successful connect -- a server that
    accepts and then immediately drops us would otherwise spin at full speed.
    """

    backoff = INITIAL_BACKOFF_SECONDS
    while True:
        try:
            async with websockets.connect(build_url()) as socket:
                async for parsed in process_all_websocket_events(socket):
                    backoff = INITIAL_BACKOFF_SECONDS
                    yield parsed
        # Narrow on purpose: a blanket `except Exception` would swallow bugs in
        # the parsing path and retry them forever instead of raising.
        except (WebSocketException, OSError):
            await asyncio.sleep(backoff)
            backoff = min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF_SECONDS)
