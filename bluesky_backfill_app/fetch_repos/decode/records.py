"""Decode a getRepo CAR into post/like/repost/follow rows."""

from collections.abc import Iterator, Mapping
from datetime import datetime
from typing import Any

import libipld

from bluesky_backfill_app.constants import BLUESKY_START_DATE, DATA_END_DATE
from bluesky_ingestion_jetstream.constants import (
    COLLECTION_TO_RECORD_TYPE,
    FOLLOWS,
    LIKES,
    POSTS,
    RECORD_TYPES,
    REPOSTS,
    REQUIRED_KEYS,
    RecordType,
)
from bluesky_ingestion_jetstream.event_parsing.follows import parse_follow
from bluesky_ingestion_jetstream.event_parsing.likes_and_reposts import parse_like_or_repost
from bluesky_ingestion_jetstream.event_parsing.posts import parse_post
from bluesky_ingestion_jetstream.event_parsing.shared import (
    as_dict,
    as_str,
    parse_created_at,
    validate_non_null_fields,
)

RECORD_TYPE_TO_PARSER = {
    POSTS: parse_post,
    LIKES: parse_like_or_repost,
    REPOSTS: parse_like_or_repost,
    FOLLOWS: parse_follow,
}

Blocks = Mapping[bytes, Any]


def get_block(blocks: Blocks, cid: bytes) -> Any:
    try:
        return blocks[cid]
    except KeyError:
        raise ValueError(f"missing block {libipld.encode_cid(cid)}") from None


def walk(blocks: Blocks, cid: bytes) -> Iterator[tuple[str, bytes]]:
    """`(collection/rkey, record CID)` for every entry under the MST node at `cid`."""

    node = as_dict(get_block(blocks, cid))
    if node["l"] is not None:
        yield from walk(blocks, node["l"])
    key = b""
    for entry in node["e"]:
        key = key[: entry["p"]] + entry["k"]
        yield key.decode(), entry["v"]
        if entry["t"] is not None:
            yield from walk(blocks, entry["t"])


def build_row(
    record_type: RecordType,
    did: str,
    key: str,
    cid: bytes,
    record: dict,
    rev: str | None,
    ingested_at: datetime,
) -> dict | None:
    """Row for one record, or None if it's outside the date range or missing required fields.

    One record per row; `decode` collects them into per-type lists. e.g. a like:
        {
            "uri": "at://did:plc:abc/app.bsky.feed.like/3kxyz",
            "did": "did:plc:abc",
            "cid": "bafyrei...",
            "rev": "3kxyzrev",
            "created_at": datetime(2025, 3, 1, 12, 0, tzinfo=UTC),
            "ingested_at": datetime(2026, 9, 16, 9, 30, tzinfo=UTC),
            "subject_uri": "at://did:plc:def/app.bsky.feed.post/3kabc",
            "subject_cid": "bafyrei...",
        }
    """

    created_at = parse_created_at(record.get("createdAt"))
    if created_at is not None and not BLUESKY_START_DATE <= created_at.date() <= DATA_END_DATE:
        return None
    row = {
        "uri": f"at://{did}/{key}",
        "did": did,
        "cid": libipld.encode_cid(cid),
        "rev": rev,
        "created_at": created_at,
        "ingested_at": ingested_at,
    } | RECORD_TYPE_TO_PARSER[record_type](record)
    return row if validate_non_null_fields(row, REQUIRED_KEYS[record_type]) else None


def decode(did: str, car_bytes: bytes, ingested_at: datetime) -> dict[RecordType, list[dict]]:
    header, blocks = libipld.decode_car(car_bytes)
    commit = as_dict(get_block(blocks, header["roots"][0]))
    if commit.get("did") != did:
        raise ValueError(f"CAR is for {commit.get('did')!r}, not {did!r}")
    rev = as_str(commit.get("rev"))

    rows: dict[RecordType, list[dict]] = {record_type: [] for record_type in RECORD_TYPES}
    for key, cid in walk(blocks, commit["data"]):
        record_type = COLLECTION_TO_RECORD_TYPE.get(key.partition("/")[0])
        if record_type is None:
            continue
        record = as_dict(get_block(blocks, cid))
        row = build_row(record_type, did, key, cid, record, rev, ingested_at)
        if row is not None:
            rows[record_type].append(row)
    return rows
