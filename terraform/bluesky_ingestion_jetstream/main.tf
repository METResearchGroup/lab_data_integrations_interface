terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Its own bucket, not the warehouse: state wants versioning, which the
  # warehouse deliberately does not have, and a stack should not hold the
  # state that describes it. Created out of band.
  backend "s3" {
    bucket       = "lab-data-integrations-interface-tfstate"
    key          = "bluesky_ingestion_jetstream/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region
}

# ---------------------------------------------------------------------------
# Variables
#
# These values are duplicated in `bluesky_ingestion_jetstream/aws/constants.py`.
# Terraform creates the container; PyIceberg addresses it by name at runtime, so
# a change here is only half a change until that file matches.
# ---------------------------------------------------------------------------

variable "aws_region" {
  default = "us-east-2"
}

variable "s3_bucket" {
  default = "lab-data-integrations-interface"
}

variable "s3_prefix" {
  description = "Warehouse root. Each record type gets its own table directory beneath it."
  default     = "bluesky/raw"
}

variable "glue_database" {
  description = "Glue database names cannot contain `/`, so this is independent of s3_prefix."
  default     = "bluesky_raw"
}

variable "cursor_table" {
  description = "Holds the Jetstream resume cursor: one item, keyed by stream."
  default     = "bluesky_jetstream_cursor"
}

# ---------------------------------------------------------------------------
# S3 — the Iceberg warehouse
#
# Versioning is left off. Iceberg already keeps history through snapshots, and
# it rewrites metadata.json on every commit, so bucket versioning would retain a
# noncurrent version per commit — thousands a day — that nothing ever reads.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "warehouse" {
  bucket = var.s3_bucket
}

resource "aws_s3_bucket_public_access_block" "warehouse" {
  bucket = aws_s3_bucket.warehouse.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------------------
# Glue catalog database
#
# The database only. The four Iceberg tables are created once by
# `python -m bluesky_ingestion_jetstream.aws.bootstrap` and are deliberately not
# Terraform resources: Iceberg rewrites a table's schema, partition spec, and
# snapshot pointer on every commit, which an `aws_glue_catalog_table` would read
# as drift and revert on the next apply.
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_database" "bluesky_raw" {
  name = var.glue_database

  # Not read by the pipeline — `create_table` passes `location` explicitly — but
  # it makes the catalog entry point at the same place the tables actually live.
  location_uri = "s3://${aws_s3_bucket.warehouse.bucket}/${var.s3_prefix}"
}

# ---------------------------------------------------------------------------
# DynamoDB — the resume cursor
#
# Unlike the Iceberg tables this is a Terraform resource: nothing rewrites its
# shape at runtime, only the one item it holds. On-demand billing because the
# load is two requests a minute.
# ---------------------------------------------------------------------------

resource "aws_dynamodb_table" "jetstream_cursor" {
  name         = var.cursor_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "stream_id"

  attribute {
    name = "stream_id"
    type = "S"
  }
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "s3_bucket_name" {
  value = aws_s3_bucket.warehouse.bucket
}

output "warehouse_uri" {
  value = "s3://${aws_s3_bucket.warehouse.bucket}/${var.s3_prefix}"
}

output "glue_database_name" {
  value = aws_glue_catalog_database.bluesky_raw.name
}

output "cursor_table_name" {
  value = aws_dynamodb_table.jetstream_cursor.name
}
