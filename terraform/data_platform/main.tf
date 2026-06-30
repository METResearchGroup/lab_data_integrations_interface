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
# S3 bucket — stores raw ingestion data and Athena query results
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

resource "aws_s3_bucket_lifecycle_configuration" "data_platform" {
  bucket = aws_s3_bucket.data_platform.id

  # Dedup results are only needed during warm() — expire quickly
  rule {
    id     = "expire-athena-results-dedup"
    status = "Enabled"

    filter {
      prefix = "athena-results/dedup/"
    }

    expiration {
      days = 1
    }
  }

  # OLAP results back the presigned download URL — keep long enough for users to download
  rule {
    id     = "expire-athena-results-olap"
    status = "Enabled"

    filter {
      prefix = "athena-results/olap/"
    }

    expiration {
      days = 7
    }
  }
}

# ---------------------------------------------------------------------------
# Glue catalog database
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_database" "data_platform" {
  name = "lab_data_integrations_interface"
}

# ---------------------------------------------------------------------------
# Athena workgroups
# ---------------------------------------------------------------------------

# Internal platform operations: dedup warm(), partition registration
resource "aws_athena_workgroup" "data_platform" {
  name = "lab-data-integrations-interface"

  configuration {
    result_configuration {
      output_location = "s3://${aws_s3_bucket.data_platform.bucket}/athena-results/dedup/"
    }
  }
}

# OLAP queries served by the backend API
resource "aws_athena_workgroup" "olap" {
  name = "lab-data-integrations-interface-olap"

  configuration {
    result_configuration {
      output_location = "s3://${aws_s3_bucket.data_platform.bucket}/athena-results/olap/"
    }
  }
}

# ---------------------------------------------------------------------------
# DynamoDB — pipeline run records (one item per orchestrator invocation)
# ---------------------------------------------------------------------------

resource "aws_dynamodb_table" "pipeline_runs" {
  name         = "lab-data-integrations-interface-pipeline-runs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pipeline_run_id"

  attribute {
    name = "pipeline_run_id"
    type = "S"
  }

  attribute {
    name = "dataset_id"
    type = "S"
  }

  attribute {
    name = "started_at"
    type = "S"
  }

  global_secondary_index {
    name            = "dataset_id-started_at-index"
    hash_key        = "dataset_id"
    range_key       = "started_at"
    projection_type = "ALL"
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

output "athena_workgroup_name" {
  value = aws_athena_workgroup.data_platform.name
}

output "athena_olap_workgroup_name" {
  value = aws_athena_workgroup.olap.name
}

output "pipeline_runs_table_name" {
  value = aws_dynamodb_table.pipeline_runs.name
}
