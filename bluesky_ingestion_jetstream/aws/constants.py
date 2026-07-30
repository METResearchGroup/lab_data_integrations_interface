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
