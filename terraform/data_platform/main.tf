terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  default = "us-east-2"
}

# ---------------------------------------------------------------------------
# S3 bucket — stores raw ingestion data and dedupe ID files
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "data_platform" {
  bucket = "lab-data-integrations-interface"
}

resource "aws_s3_bucket_public_access_block" "data_platform" {
  bucket = aws_s3_bucket.data_platform.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "data_platform" {
  bucket = aws_s3_bucket.data_platform.id
  versioning_configuration {
    status = "Disabled"
  }
}

# Expire Athena query result files after 1 day — they're only needed during warm()
resource "aws_s3_bucket_lifecycle_configuration" "data_platform" {
  bucket = aws_s3_bucket.data_platform.id

  rule {
    id     = "expire-athena-results"
    status = "Enabled"

    filter {
      prefix = "athena-results/"
    }

    expiration {
      days = 1
    }
  }
}

# ---------------------------------------------------------------------------
# Glue catalog — schema for Athena to query dedupe ID files
#
# S3 layout:
#   s3://lab-data-integrations-interface/dedupe/platform={platform}/run={run}/seen_ids.parquet
#
# Each file contains one column (id: string) — the post URIs/IDs for that run.
# Athena prunes by platform partition so queries only scan the relevant folder.
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_database" "data_platform" {
  name = "lab_data_integrations_interface"
}

resource "aws_glue_catalog_table" "dedupe_seen_ids" {
  database_name = aws_glue_catalog_database.data_platform.name
  name          = "dedupe_seen_ids"

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data_platform.bucket}/dedupe/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "id"
      type = "string"
    }
  }

  partition_keys {
    name = "platform"
    type = "string"
  }

  partition_keys {
    name = "run"
    type = "string"
  }
}

# ---------------------------------------------------------------------------
# Athena workgroup — controls query result output location
# ---------------------------------------------------------------------------

resource "aws_athena_workgroup" "data_platform" {
  name = "lab-data-integrations-interface"

  configuration {
    result_configuration {
      output_location = "s3://${aws_s3_bucket.data_platform.bucket}/athena-results/"
    }
  }
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "s3_bucket_name" {
  value = aws_s3_bucket.data_platform.bucket
}

output "glue_database_name" {
  value = aws_glue_catalog_database.data_platform.name
}

output "glue_table_name" {
  value = aws_glue_catalog_table.dedupe_seen_ids.name
}

output "athena_workgroup_name" {
  value = aws_athena_workgroup.data_platform.name
}
