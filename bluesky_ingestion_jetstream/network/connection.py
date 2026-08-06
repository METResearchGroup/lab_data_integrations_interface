"""Jetstream WebSocket connection."""

import asyncio
import json
import logging
from collections.abc import AsyncIterable, AsyncIterator, Callable
from dataclasses import dataclass
from urllib.parse import urlencode

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

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
from bluesky_ingestion_jetstream.telemetry.instruments import record_connection_failure
from bluesky_ingestion_jetstream.telemetry.state import STREAM_STATE

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One event's position in the stream, and its row when we store that kind.

    Examples:
        StreamEvent(1784789293411372, ("likes", {"uri": ..., "did": ...}))
        StreamEvent(1784789293411373, None)
    """

    time_us: int
    parsed: tuple[str, dict] | None


def build_url(cursor: int | None = None) -> str:
    """The subscribe URL, filtered server-side to the collections we store."""

    params = [("wantedCollections", collection) for collection in WANTED_COLLECTIONS]
    if cursor is not None:
        params.append(("cursor", str(cursor)))
    return f"{JETSTREAM_ENDPOINT}?{urlencode(params)}"


def is_commit(event: object) -> bool:
    """Whether this event is a commit. Identity and account events are not."""

    return isinstance(event, dict) and event.get("kind") == "commit"


def event_time_us(event: object) -> int | None:
    """The broker's timestamp for an event, or None if the frame has no usable one."""

    if not isinstance(event, dict):
        return None
    time_us = event.get("time_us")
    # bools are ints, and a `True` position is junk rather than 1 microsecond.
    if not isinstance(time_us, int) or isinstance(time_us, bool):
        return None
    return time_us


async def process_all_websocket_events(
    messages: AsyncIterable[str | bytes],
) -> AsyncIterator[StreamEvent]:
    """Yield a StreamEvent per frame we can place, stored or dropped.

    Dropped events are yielded too, with `parsed` None, so the cursor keeps
    moving when little of what we store is flowing. A frame with no usable
    `time_us` is skipped entirely: there is no position to record.

    Takes any async iterable rather than a socket, so it can be exercised with a
    plain list of messages.
    """

    async for message in messages:
        # Frames arrive as raw text, so this is the one place we deserialize.
        try:
            event = json.loads(message)
        except json.JSONDecodeError:
            continue

        time_us = event_time_us(event)
        if time_us is None:
            continue

        # off-chance that data has a null field
        parsed = process_commit_event(event) if is_commit(event) else None
        yield StreamEvent(time_us, parsed)


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


def disconnect_reason(error: BaseException) -> str:
    """A label for why the socket dropped.

    Close code or exception class, never the message: an unbounded label value
    turns one series into thousands.
    """

    if isinstance(error, ConnectionClosed):
        close = error.rcvd or error.sent
        if close is not None:
            return f"close_{close.code}"
    return type(error).__name__


async def stream_events(
    resume_from: Callable[[], int | None] = lambda: None,
) -> AsyncIterator[StreamEvent]:
    """Connect to Jetstream and yield its events, reconnecting with exponential backoff."""

    backoff = INITIAL_BACKOFF_SECONDS
    while True:
        try:
            async with websockets.connect(build_url(resume_from())) as socket:
                STREAM_STATE.connected = True
                async for event in process_all_websocket_events(socket):
                    backoff = INITIAL_BACKOFF_SECONDS
                    yield event
        # Narrow on purpose: a blanket `except Exception` would swallow bugs in
        # the parsing path and retry them forever instead of raising.
        except (WebSocketException, OSError) as error:
            # Logged as well as counted: the counter says how often, the log line
            # says when, which is what the dashboard needs to name a live outage.
            reason = disconnect_reason(error)
            STREAM_STATE.connected = False
            logger.warning("jetstream disconnected: %s", reason)
            record_connection_failure(reason)
            await asyncio.sleep(backoff)
            backoff = min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF_SECONDS)
