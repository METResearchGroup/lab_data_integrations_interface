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
# S3 bucket — stores the SQLite dedup file for the S3+SQLite backend
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "dedup_experiment" {
  bucket        = "lab-data-integrations-dedup-experiment-use2"
  force_destroy = true  # allows destroy even if bucket has objects
}

resource "aws_s3_bucket_versioning" "dedup_experiment" {
  bucket = aws_s3_bucket.dedup_experiment.id
  versioning_configuration {
    status = "Disabled"  # not needed for an experiment
  }
}

# ---------------------------------------------------------------------------
# DynamoDB table — stores seen URIs for the DynamoDB backend
# ---------------------------------------------------------------------------

resource "aws_dynamodb_table" "seen_ids" {
  name         = "lab-data-integrations-dedup-experiment-seen-ids"
  billing_mode = "PAY_PER_REQUEST"  # pay per request, no capacity planning

  hash_key = "uri"

  attribute {
    name = "uri"
    type = "S"
  }
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "s3_bucket_name" {
  value = aws_s3_bucket.dedup_experiment.bucket
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.seen_ids.name
}

output "dynamodb_table_arn" {
  value = aws_dynamodb_table.seen_ids.arn
}
