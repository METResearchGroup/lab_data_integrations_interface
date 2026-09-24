# ---------------------------------------------------------------------------
# Landing Glue tables
#
# Plain Parquet tables over the landing prefix, so Athena can read what
# `fetch_repos` writes. `dt` uses partition projection: Athena derives the
# partition paths from the template at query time, so new flushes need no
# catalog update.
# ---------------------------------------------------------------------------

variable "s3_bucket" {
  default = "lab-data-integrations-interface"
}

variable "landing_prefix" {
  description = "Mirrors `LANDING_PREFIX` in `bluesky_backfill_app/fetch_repos/constants.py`."
  default     = "landing/bluesky/backfill"
}

variable "landing_glue_database" {
  default = "bluesky_backfill_landing"
}

variable "landing_start_date" {
  description = "First landing `dt`. Projection lists no partitions before it."
  default     = "2026-09-15"
}

locals {
  # Columns mirror `RECORD_TYPE_TO_SCHEMA` in
  # `bluesky_ingestion_jetstream/schemas/arrow_schemas.py`; hand-kept.
  landing_common_columns = [
    { name = "uri", type = "string" },
    { name = "did", type = "string" },
    { name = "cid", type = "string" },
    { name = "rev", type = "string" },
    { name = "created_at", type = "timestamp" },
    { name = "ingested_at", type = "timestamp" },
    { name = "run_id", type = "string" },
  ]

  landing_subject_columns = [
    { name = "subject_uri", type = "string" },
    { name = "subject_cid", type = "string" },
  ]

  landing_columns = {
    posts = concat(local.landing_common_columns, [
      { name = "text", type = "string" },
      { name = "langs", type = "array<string>" },
      { name = "reply_root_uri", type = "string" },
      { name = "reply_parent_uri", type = "string" },
      { name = "embed_type", type = "string" },
    ])
    likes   = concat(local.landing_common_columns, local.landing_subject_columns)
    reposts = concat(local.landing_common_columns, local.landing_subject_columns)
    follows = concat(local.landing_common_columns, [
      { name = "subject_did", type = "string" },
    ])
  }
}

resource "aws_glue_catalog_database" "landing" {
  name = var.landing_glue_database
}

resource "aws_glue_catalog_table" "landing" {
  for_each = local.landing_columns

  database_name = aws_glue_catalog_database.landing.name
  name          = each.key
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL                      = "TRUE"
    classification                = "parquet"
    "projection.enabled"          = "true"
    "projection.dt.type"          = "date"
    "projection.dt.format"        = "yyyy-MM-dd"
    "projection.dt.range"         = "${var.landing_start_date},NOW"
    "projection.dt.interval"      = "1"
    "projection.dt.interval.unit" = "DAYS"
    "storage.location.template"   = "s3://${var.s3_bucket}/${var.landing_prefix}/${each.key}/dt=$${dt}/"
  }

  partition_keys {
    name = "dt"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${var.s3_bucket}/${var.landing_prefix}/${each.key}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    dynamic "columns" {
      for_each = each.value
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }
}

output "landing_glue_database_name" {
  value = aws_glue_catalog_database.landing.name
}
