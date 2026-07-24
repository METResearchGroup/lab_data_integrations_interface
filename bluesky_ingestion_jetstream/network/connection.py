"""Jetstream WebSocket connection."""

import json
from collections.abc import AsyncIterator
from urllib.parse import urlencode

import websockets

from bluesky_ingestion_jetstream.constants import (
    COLLECTION_TO_RECORD_TYPE,
    FOLLOWS,
    JETSTREAM_ENDPOINT,
    LIKES,
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


async def stream_events() -> AsyncIterator[tuple[str, dict]]:
    """Connect to Jetstream and yield (record_type, row) pairs for commits."""

    async with websockets.connect(build_url()) as socket:
        async for message in socket:
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
