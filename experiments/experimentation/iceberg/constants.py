"""Tunables and fixed identifiers for the Iceberg write-amplification experiment."""

from __future__ import annotations

# --- Bluesky Jetstream -------------------------------------------------------

JETSTREAM_ENDPOINT = "wss://jetstream2.us-east.bsky.network/subscribe"

# Jetstream collection NSID -> the short record type we bucket it into.
COLLECTIONS: dict[str, str] = {
    "app.bsky.feed.post": "posts",
    "app.bsky.feed.like": "likes",
    "app.bsky.feed.repost": "reposts",
    "app.bsky.graph.follow": "follows",
}

RECORD_TYPES: tuple[str, ...] = ("posts", "likes", "reposts", "follows")

DEFAULT_CAPTURE_SECONDS = 600  # 10 minutes

# --- S3 / Glue ---------------------------------------------------------------

S3_BUCKET = "lab-data-integrations-interface"
S3_EXPERIMENT_PREFIX = "experiments/iceberg"
AWS_REGION = "us-east-2"

# Dedicated Glue database so the experiment never touches `default`.
GLUE_DATABASE = "iceberg_experiments"

# --- Write path --------------------------------------------------------------

DEFAULT_FLUSH_SECONDS = 60  # -> 10 commits per table across a 10-minute replay

# Jetstream `createdAt` is client-supplied and occasionally garbage (epoch 0,
# year 2100). Anything further than this from the broker-side ingest timestamp
# falls back to ingest time so we don't spawn junk daily partitions.
MAX_CREATED_AT_SKEW_SECONDS = 86_400

# --- Pricing (us-east-2, USD) ------------------------------------------------
# Used to turn measured request counts into a cost model. Verify against
# current AWS pricing before quoting these numbers externally.

COST_PER_PUT_REQUEST = 0.005 / 1_000  # PUT, COPY, POST, LIST
COST_PER_GET_REQUEST = 0.0004 / 1_000  # GET, SELECT, and all other requests
COST_PER_DELETE_REQUEST = 0.0  # DELETE and CANCEL are free
COST_PER_GLUE_REQUEST = 1.00 / 100_000
COST_PER_GB_MONTH_STANDARD = 0.023

# S3 API operations billed at the (expensive) PUT/LIST rate. Everything else
# that isn't a DELETE falls through to the GET rate.
PUT_TIER_OPERATIONS: frozenset[str] = frozenset(
    {
        "PutObject",
        "CopyObject",
        "PostObject",
        "ListObjects",
        "ListObjectsV2",
        "ListBuckets",
        "ListMultipartUploads",
        "ListParts",
        "CreateMultipartUpload",
        "UploadPart",
        "UploadPartCopy",
        "CompleteMultipartUpload",
    }
)

DELETE_TIER_OPERATIONS: frozenset[str] = frozenset(
    {"DeleteObject", "DeleteObjects", "AbortMultipartUpload"}
)

# --- Phases ------------------------------------------------------------------

PHASE_RAW_WRITE = "raw_write"
PHASE_ICEBERG_APPEND = "iceberg_append"
PHASE_COMPACT_DEDUP = "compact_dedup"
PHASE_EXPIRE_METADATA = "expire_metadata"

PHASES: tuple[str, ...] = (
    PHASE_RAW_WRITE,
    PHASE_ICEBERG_APPEND,
    PHASE_COMPACT_DEDUP,
    PHASE_EXPIRE_METADATA,
)
