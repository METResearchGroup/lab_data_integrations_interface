"""AWS identifiers and Iceberg table configuration for this pipeline."""

from bluesky_ingestion_jetstream.constants import RECORD_TYPES

AWS_REGION = "us-east-2"
S3_BUCKET = "lab-data-integrations-interface"
S3_PREFIX = "bluesky/raw"

# Created by Terraform (`terraform/bluesky_ingestion_jetstream/main.tf`), not by
# this package.
GLUE_DATABASE = "bluesky_raw"

# One table per record type, each rooted at its own prefix. Glue database names
# cannot contain `/`, so the catalog name and the S3 path are independent and the
# location has to be passed explicitly at creation.
TABLE_LOCATIONS = {
    record_type: f"s3://{S3_BUCKET}/{S3_PREFIX}/{record_type}" for record_type in RECORD_TYPES
}

# Applied at table creation. Iceberg stores these in table metadata, so editing a
# value here has no effect on tables that already exist.
TABLE_PROPERTIES = {
    "format-version": "2",
    "write.parquet.compression-codec": "zstd",
    "write.target-file-size-bytes": str(256 * 1024 * 1024),
    # Iceberg's default salts a hash into the data path to spread load across S3
    # prefixes. At this volume the throttling that avoids is not a real risk, and
    # the cost is that the `created_at_day=.../` layout stops being browsable.
    "write.object-storage.enabled": "false",
    "write.metadata.delete-after-commit.enabled": "true",
    "write.metadata.previous-versions-max": "100",
    # Inert while ingestion is append-only -- delete files come only from
    # DELETE/UPDATE/MERGE, and nothing issues those yet. Set now because the
    # duplicate URIs backfill will introduce are exactly the case they exist for,
    # and rewriting whole data files to retract a few rows is the wrong trade.
    # Note that PyIceberg does not write delete files, so whatever runs that
    # merge will have to be Athena or Spark.
    "write.delete.mode": "merge-on-read",
    "write.update.mode": "merge-on-read",
    "write.merge.mode": "merge-on-read",
}

# The field name is Iceberg's own default for a `day()` transform, spelled out
# because it is what appears on disk as `created_at_day=2026-07-16/`.
PARTITION_SOURCE_COLUMN = "created_at"
PARTITION_FIELD_NAME = "created_at_day"

# ---------------------------------------------------------------------------
# Client bounds
#
# The flush is synchronous inside the async read loop, so every second spent in
# a commit is a second the Jetstream socket is not being drained. That makes the
# worst-case duration of one commit a real constraint, not a detail.
#
# PyIceberg builds its Glue client with `standard` retry mode and
# `max_attempts=10` (pyiceberg/catalog/glue.py:131) over botocore's default 60s
# read timeout, so an unbounded retry loop sits *underneath* every append. Three
# outer attempts only means three requests if that inner loop is capped too;
# left alone, "3 retries" can block for minutes.
# ---------------------------------------------------------------------------

GLUE_MAX_ATTEMPTS = 2
GLUE_CONNECT_TIMEOUT_SECONDS = 3.0
GLUE_READ_TIMEOUT_SECONDS = 10.0

# PyIceberg passes these through to the PyArrow S3 filesystem
# (pyiceberg/io/pyarrow.py:445-448). Longer than the Glue timeouts because these
# cover data transfer, not a metadata call.
S3_CONNECT_TIMEOUT_SECONDS = 3.0
S3_REQUEST_TIMEOUT_SECONDS = 15.0

# ---------------------------------------------------------------------------
# Commit retry
#
# Three attempts, so two sleeps: roughly 1s then 2s with full jitter. Deliberately
# short. A longer budget would ride out a Glue throttling episode, but it would
# do so by stalling the socket, and a batch that reaches the dead letter is
# recoverable while a dropped connection is not.
# ---------------------------------------------------------------------------

COMMIT_MAX_ATTEMPTS = 3
COMMIT_INITIAL_DELAY_SECONDS = 1.0
COMMIT_MAX_DELAY_SECONDS = 8.0

# Identifies one flush inside the snapshot summary, so a retry can tell "the
# commit failed" from "the commit succeeded and the response was lost".
FLUSH_ID_PROPERTY = "flush_id"

# ---------------------------------------------------------------------------
# Dead letter
#
# Outside `S3_PREFIX` on purpose, and above `bluesky/` rather than inside it.
# These files are unreferenced by any Iceberg table by definition, which is
# exactly what orphan-file cleanup deletes -- so they must not live anywhere
# under the warehouse root.
# ---------------------------------------------------------------------------

DEAD_LETTER_PREFIX = "dead_letter/bluesky/raw"
DEAD_LETTER_ROOT = f"{S3_BUCKET}/{DEAD_LETTER_PREFIX}"
