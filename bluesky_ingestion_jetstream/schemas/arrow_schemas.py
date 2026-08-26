"""PyArrow schemas for the commit tables."""

import pyarrow as pa

from bluesky_ingestion_jetstream.constants import FOLLOWS, LIKES, POSTS, REPOSTS, RecordType

# Common fields that are stamped on by the writer at flush time rather than
# produced by the parsers.
WRITE_STAMPED_FIELDS = [
    pa.field("run_id", pa.string()),
]

# Present in all four tables.
COMMON_FIELDS = [
    pa.field("uri", pa.string()),
    pa.field("did", pa.string()),
    pa.field("cid", pa.string()),
    pa.field("rev", pa.string()),
    pa.field("created_at", pa.timestamp("us", tz="UTC")),
    pa.field("ingested_at", pa.timestamp("us", tz="UTC")),
    *WRITE_STAMPED_FIELDS,
]

POST_SCHEMA: pa.Schema = pa.schema(
    [
        *COMMON_FIELDS,
        pa.field("text", pa.string()),
        pa.field("langs", pa.list_(pa.string())),
        pa.field("reply_root_uri", pa.string()),
        pa.field("reply_parent_uri", pa.string()),
        pa.field("embed_type", pa.string()),
    ]
)

LIKE_SCHEMA: pa.Schema = pa.schema(
    [
        *COMMON_FIELDS,
        pa.field("subject_uri", pa.string()),
        pa.field("subject_cid", pa.string()),
    ]
)

# Identical record shape to likes, but a separate table.
REPOST_SCHEMA: pa.Schema = LIKE_SCHEMA

FOLLOW_SCHEMA: pa.Schema = pa.schema([*COMMON_FIELDS, pa.field("subject_did", pa.string())])

RECORD_TYPE_TO_SCHEMA: dict[RecordType, pa.Schema] = {
    POSTS: POST_SCHEMA,
    LIKES: LIKE_SCHEMA,
    REPOSTS: REPOST_SCHEMA,
    FOLLOWS: FOLLOW_SCHEMA,
}
