"""Iceberg schemas for the four Bluesky record types, plus Jetstream parsing.

Each record type gets its own table, all sharing a common header (ids 1-10) and
adding type-specific columns from id 11. Every table is partitioned by
``days(created_at)``.

**Field ids must be contiguous from 1.** ``Catalog.create_table`` renumbers a
schema's fields sequentially, and Iceberg resolves columns by id, not by name.
Declaring a gap (say, jumping to id 20) means the table is created with the
renumbered ids while writes built from this module's schema still stamp the
declared ids into the Parquet footers -- so reads look up ids that are not
there and silently return NULL for every affected column. ``test_schemas.py``
enforces contiguity, and ``iceberg_writer`` builds its Arrow tables from the
*table's* schema rather than this one, so the two cannot drift.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import DayTransform
from pyiceberg.types import (
    BooleanType,
    IntegerType,
    ListType,
    NestedField,
    StringType,
    TimestamptzType,
)

from experimentation.iceberg import constants

# Field id of `created_at` -- the partition source for every table.
CREATED_AT_FIELD_ID = 8

_COMMON_FIELDS = [
    NestedField(1, "uri", StringType(), required=True),
    NestedField(2, "did", StringType(), required=True),
    NestedField(3, "collection", StringType(), required=True),
    NestedField(4, "rkey", StringType(), required=True),
    NestedField(5, "cid", StringType(), required=False),
    NestedField(6, "rev", StringType(), required=False),
    NestedField(7, "operation", StringType(), required=True),
    NestedField(CREATED_AT_FIELD_ID, "created_at", TimestamptzType(), required=True),
    NestedField(9, "ingested_at", TimestamptzType(), required=True),
    # True when `createdAt` was unusable and we substituted the ingest timestamp.
    NestedField(10, "created_at_fallback", BooleanType(), required=True),
]

SCHEMAS: dict[str, Schema] = {
    "posts": Schema(
        *_COMMON_FIELDS,
        NestedField(11, "text", StringType(), required=False),
        NestedField(
            12,
            "langs",
            # Nested ids are assigned after every top-level field, so the list
            # element follows text_length (16), not langs (12).
            ListType(element_id=17, element_type=StringType(), element_required=False),
            required=False,
        ),
        NestedField(13, "reply_root_uri", StringType(), required=False),
        NestedField(14, "reply_parent_uri", StringType(), required=False),
        NestedField(15, "embed_type", StringType(), required=False),
        NestedField(16, "text_length", IntegerType(), required=False),
    ),
    "likes": Schema(
        *_COMMON_FIELDS,
        NestedField(11, "subject_uri", StringType(), required=False),
        NestedField(12, "subject_cid", StringType(), required=False),
    ),
    "reposts": Schema(
        *_COMMON_FIELDS,
        NestedField(11, "subject_uri", StringType(), required=False),
        NestedField(12, "subject_cid", StringType(), required=False),
    ),
    "follows": Schema(
        *_COMMON_FIELDS,
        NestedField(11, "subject_did", StringType(), required=False),
    ),
}

PARTITION_SPEC = PartitionSpec(
    PartitionField(
        source_id=CREATED_AT_FIELD_ID,
        field_id=1000,
        transform=DayTransform(),
        name="created_at_day",
    )
)


def _parse_created_at(raw: Any, ingested_at: datetime) -> tuple[datetime, bool]:
    """Resolve a record's ``createdAt``, falling back to ingest time when unusable.

    Bluesky ``createdAt`` is client-supplied. Malformed or wildly skewed values
    would each open a junk daily partition, so anything more than
    ``MAX_CREATED_AT_SKEW_SECONDS`` from the broker timestamp is rejected.

    Returns the timestamp and whether the fallback was used.
    """
    if not isinstance(raw, str) or not raw:
        return ingested_at, True
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ingested_at, True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    if abs((parsed - ingested_at).total_seconds()) > constants.MAX_CREATED_AT_SKEW_SECONDS:
        return ingested_at, True
    return parsed, False


def _as_dict(value: Any) -> dict[str, Any]:
    """Return ``value`` when it is a dict, otherwise an empty dict."""
    return value if isinstance(value, dict) else {}


def _subject_uri(record: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extract (uri, cid) from a like/repost subject, which is a strongref."""
    subject = _as_dict(record.get("subject"))
    return subject.get("uri"), subject.get("cid")


def _embed_type(record: dict[str, Any]) -> str | None:
    return _as_dict(record.get("embed")).get("$type")


def parse_event(event: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Turn a raw Jetstream message into ``(record_type, row)``.

    Returns ``None`` for anything that isn't a commit on a collection we track --
    identity and account events, and collections outside ``COLLECTIONS``.
    """
    if event.get("kind") != "commit":
        return None
    commit = event.get("commit")
    if not isinstance(commit, dict):
        return None

    collection = commit.get("collection", "")
    record_type = constants.COLLECTIONS.get(collection)
    if record_type is None:
        return None

    did = event.get("did", "")
    rkey = commit.get("rkey", "")
    if not did or not rkey:
        return None

    time_us = event.get("time_us") or 0
    ingested_at = datetime.fromtimestamp(time_us / 1_000_000, tz=UTC)

    # Deletes carry no record body; they still matter for dedup realism.
    record = _as_dict(commit.get("record"))

    created_at, fallback = _parse_created_at(record.get("createdAt"), ingested_at)

    row: dict[str, Any] = {
        "uri": f"at://{did}/{collection}/{rkey}",
        "did": did,
        "collection": collection,
        "rkey": rkey,
        "cid": commit.get("cid"),
        "rev": commit.get("rev"),
        "operation": commit.get("operation", "unknown"),
        "created_at": created_at,
        "ingested_at": ingested_at,
        "created_at_fallback": fallback,
    }

    if record_type == "posts":
        text = record.get("text")
        langs = record.get("langs")
        reply = _as_dict(record.get("reply"))
        root = _as_dict(reply.get("root"))
        parent = _as_dict(reply.get("parent"))
        row.update(
            {
                "text": text,
                "langs": langs if isinstance(langs, list) else None,
                "reply_root_uri": root.get("uri"),
                "reply_parent_uri": parent.get("uri"),
                "embed_type": _embed_type(record),
                "text_length": len(text) if isinstance(text, str) else None,
            }
        )
    elif record_type in ("likes", "reposts"):
        uri, cid = _subject_uri(record)
        row.update({"subject_uri": uri, "subject_cid": cid})
    elif record_type == "follows":
        row["subject_did"] = (
            record.get("subject") if isinstance(record.get("subject"), str) else None
        )

    return record_type, row
