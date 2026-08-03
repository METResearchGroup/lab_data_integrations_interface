"""AWS identifiers and Iceberg table configuration for this pipeline."""

from bluesky_ingestion_jetstream.constants import RECORD_TYPES

AWS_REGION = "us-east-2"
S3_BUCKET = "lab-data-integrations-interface"
S3_PREFIX = "bluesky/raw"

# Created by Terraform (`terraform/bluesky_ingestion_jetstream/main.tf`).
GLUE_DATABASE = "bluesky_raw"

# One table per record type. Glue names cannot contain `/`, so the location is
# passed explicitly at creation.
TABLE_LOCATIONS = {
    record_type: f"s3://{S3_BUCKET}/{S3_PREFIX}/{record_type}" for record_type in RECORD_TYPES
}

# Applied at table creation only; edits here do not reach existing tables.
TABLE_PROPERTIES = {
    "format-version": "2",
    "write.parquet.compression-codec": "zstd",
    "write.target-file-size-bytes": str(256 * 1024 * 1024),
    # Iceberg's default salts a hash into the data path; unnecessary at this
    # volume, and it costs a browsable `created_at_day=.../` layout.
    "write.object-storage.enabled": "false",
    "write.metadata.delete-after-commit.enabled": "true",
    "write.metadata.previous-versions-max": "100",
    # Inert while ingestion is append-only. Set now for the duplicates backfill
    # will introduce; PyIceberg cannot write delete files, so that merge needs
    # Athena or Spark.
    "write.delete.mode": "merge-on-read",
    "write.update.mode": "merge-on-read",
    "write.merge.mode": "merge-on-read",
}

# Iceberg's default name for a `day()` transform, as it appears on disk.
PARTITION_SOURCE_COLUMN = "created_at"
PARTITION_FIELD_NAME = "created_at_day"

# ---------------------------------------------------------------------------
# Client bounds
#
# Overrides PyIceberg's Glue defaults
# ---------------------------------------------------------------------------

GLUE_MAX_ATTEMPTS = 2
GLUE_CONNECT_TIMEOUT_SECONDS = 3.0
GLUE_READ_TIMEOUT_SECONDS = 10.0

# Passed to the PyArrow S3 filesystem (pyiceberg/io/pyarrow.py:445-448).
S3_CONNECT_TIMEOUT_SECONDS = 3.0
S3_REQUEST_TIMEOUT_SECONDS = 15.0

# ---------------------------------------------------------------------------
# Commit retry
#
# Three attempts, two sleeps
# ---------------------------------------------------------------------------

COMMIT_MAX_ATTEMPTS = 3
COMMIT_INITIAL_DELAY_SECONDS = 1.0
COMMIT_MAX_DELAY_SECONDS = 8.0

# Stamped on the snapshot, so a retry can tell a failed commit from a lost reply.
SNAPSHOT_FLUSH_ID_TAG = "flush_id"

# ---------------------------------------------------------------------------
# Dead letter
#
# Outside `S3_PREFIX`: orphan cleanup deletes unreferenced files under the
# warehouse root, and these are unreferenced by definition.
# ---------------------------------------------------------------------------

DEAD_LETTER_PREFIX = "dead_letter/bluesky/raw"
DEAD_LETTER_ROOT = f"{S3_BUCKET}/{DEAD_LETTER_PREFIX}"
