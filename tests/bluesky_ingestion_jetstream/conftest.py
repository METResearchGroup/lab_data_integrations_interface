"""Shared Jetstream event fixtures."""

import json
from datetime import UTC, datetime

import pytest

DID = "did:plc:eygmaihciaxprqvxrfvl6flk"
RKEY = "3l3qo2vuowo2b"
CID = "bafyreidc6sykmtx7dbepnvdyzsjmyzpqfsn3fzo7lgvxfwbfjhqtwrxnfu"
REV = "3l3qo2vutsw2b"

CREATED_AT_STR = "2026-07-23T06:48:11.102Z"
CREATED_AT = datetime(2026, 7, 23, 6, 48, 11, 102000, tzinfo=UTC)

# A distinct instant from CREATED_AT -- the two clocks are independent, and a test
# that shared one instant could not catch them being swapped. Shortly *after* it,
# rather than before: a create reaches the firehose after it is made, and
# `is_created_at_valid` now rejects a `created_at` more than
# MAX_CREATED_AT_SKEW ahead of the broker's clock, so a fixture ordered the other
# way would be dropped by every parser test that uses it.
TIME_US = 1784789293411372
INGESTED_AT = datetime(2026, 7, 23, 6, 48, 13, 411372, tzinfo=UTC)

# Fixed, so a test can assert the stamped value rather than merely its presence.
RUN_ID = "f47ac10b-58cc-4372-a567-0e02b2c3d479"

SUBJECT_DID = "did:plc:targetaccount0000000000"
SUBJECT_URI = "at://did:plc:abc/app.bsky.feed.post/3l3qtarget"
SUBJECT_CID = "bafyreitargetcid"

POST_COLLECTION = "app.bsky.feed.post"
LIKE_COLLECTION = "app.bsky.feed.like"
REPOST_COLLECTION = "app.bsky.feed.repost"
FOLLOW_COLLECTION = "app.bsky.graph.follow"


def make_event(
    collection: str,
    record: object,
    *,
    did: object = DID,
    rkey: object = RKEY,
    cid: object = CID,
    rev: object = REV,
    time_us: object = TIME_US,
    operation: str = "create",
    kind: str = "commit",
    drop_commit: bool = False,
) -> dict:
    """Build a Jetstream envelope, with hooks for the malformed variants."""

    event: dict = {"did": did, "kind": kind, "time_us": time_us}
    if drop_commit:
        return event

    event["commit"] = {
        "rev": rev,
        "operation": operation,
        "collection": collection,
        "rkey": rkey,
        "cid": cid,
        "record": record,
    }
    return event


def post_record(**overrides: object) -> dict:
    """A reply post with langs and an image embed."""

    record: dict[str, object] = {
        "text": "hello world",
        "langs": ["en"],
        "createdAt": CREATED_AT_STR,
        "reply": {
            "root": {"uri": "at://did:plc:abc/app.bsky.feed.post/3l3qroot"},
            "parent": {"uri": "at://did:plc:def/app.bsky.feed.post/3l3rparent"},
        },
        "embed": {"$type": "app.bsky.embed.images"},
    }
    record.update(overrides)
    return record


def interaction_record(**overrides: object) -> dict:
    """A like or repost: a createdAt plus a strongref to the post acted on."""

    record: dict[str, object] = {
        "createdAt": CREATED_AT_STR,
        "subject": {"uri": SUBJECT_URI, "cid": SUBJECT_CID},
    }
    record.update(overrides)
    return record


def follow_record(**overrides: object) -> dict:
    """A follow: `subject` is a bare DID string, not a strongref object."""

    record: dict[str, object] = {"createdAt": CREATED_AT_STR, "subject": SUBJECT_DID}
    record.update(overrides)
    return record


RECORD_BUILDERS = {
    "posts": (POST_COLLECTION, post_record),
    "likes": (LIKE_COLLECTION, interaction_record),
    "reposts": (REPOST_COLLECTION, interaction_record),
    "follows": (FOLLOW_COLLECTION, follow_record),
}


def make_rows(record_type: str, count: int) -> list[dict]:
    """Build `count` parsed rows of one record type, with distinct rkeys."""

    from bluesky_ingestion_jetstream.network.connection import process_commit_event

    collection, builder = RECORD_BUILDERS[record_type]
    rows = []
    for index in range(count):
        event = make_event(collection, builder(), rkey=f"{RKEY}{index}")
        parsed = process_commit_event(event)
        assert parsed is not None
        rows.append(parsed[1])
    return rows


def as_messages(events: list) -> list[str]:
    """Serialize events the way they arrive on the wire."""

    return [json.dumps(event) for event in events]


class MemorySink:
    """A `Sink` that collects writes in a list."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, list[dict]]] = []

    def write(self, record_type: str, rows: list[dict]) -> None:
        # Copied, so a later `Buffer.clear()` cannot empty what was recorded.
        self.writes.append((record_type, list(rows)))


@pytest.fixture
def post_event() -> dict:
    return make_event(POST_COLLECTION, post_record())


@pytest.fixture
def like_event() -> dict:
    return make_event(LIKE_COLLECTION, interaction_record())


@pytest.fixture
def repost_event() -> dict:
    return make_event(REPOST_COLLECTION, interaction_record())


@pytest.fixture
def follow_event() -> dict:
    return make_event(FOLLOW_COLLECTION, follow_record())


@pytest.fixture
def rows_factory():
    """Expose `make_rows` to buffer, writer, and main tests."""

    return make_rows
