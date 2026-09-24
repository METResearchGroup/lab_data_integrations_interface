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

# ---------------------------------------------------------------------------
# Variables
#
# Duplicated in `bluesky_backfill_app/aws/constants.py`; a change here is only
# half a change until that file matches.
# ---------------------------------------------------------------------------

variable "aws_region" {
  default = "us-east-2"
}

variable "did_table" {
  description = "One item per discovered repo, keyed by DID."
  default     = "bluesky_backfill_dids"
}

variable "cursor_table" {
  description = "The listRepos cursor and running DID count: one item, keyed by run."
  default     = "bluesky_backfill_cursor"
}

variable "queue_name" {
  default = "bluesky-backfill-dids"
}

variable "visibility_timeout_seconds" {
  description = "Time a consumer has to fetch one repo before the message reappears."
  default     = 3600
}

variable "max_receive_count" {
  description = "Deliveries before SQS moves the message to the DLQ."
  default     = 5
}

# ---------------------------------------------------------------------------
# DynamoDB
#
# On-demand: discovery writes in 10k bursts and is idle between them.
# ---------------------------------------------------------------------------

resource "aws_dynamodb_table" "backfill_dids" {
  name         = var.did_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "did"

  attribute {
    name = "did"
    type = "S"
  }

  attribute {
    name = "status_shard"
    type = "S"
  }

  # `status_shard` is `{status}#{shard}`. Sharded because a handful of status
  # values would otherwise put every write for a stage on one partition.
  global_secondary_index {
    name            = "status_index"
    hash_key        = "status_shard"
    projection_type = "KEYS_ONLY"
  }

  point_in_time_recovery {
    enabled = true
  }
}

resource "aws_dynamodb_table" "backfill_cursor" {
  name         = var.cursor_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "run_id"

  attribute {
    name = "run_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# ---------------------------------------------------------------------------
# SQS
#
# Standard, not FIFO: ordering does not matter and the DynamoDB status gates
# re-enqueueing, so consumers only need to be idempotent.
#
# The visibility timeout must cover a fetch plus the flush after it.
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "backfill_dids" {
  name                       = var.queue_name
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = 1209600

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.backfill_dids_dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

# DLQ for the queue above. Nothing consumes it.
resource "aws_sqs_queue" "backfill_dids_dlq" {
  name                      = "${var.queue_name}-dlq"
  message_retention_seconds = 1209600
}

# ---------------------------------------------------------------------------
# Shared by the merge and backfill maintenance state machines
#
# The bucket, `bluesky_raw`, and the alarm topic belong to
# `terraform/bluesky_ingestion_jetstream`; referenced by name only.
# ---------------------------------------------------------------------------

variable "s3_bucket" {
  default = "lab-data-integrations-interface"
}

variable "raw_glue_database" {
  default = "bluesky_raw"
}

variable "raw_prefix" {
  default = "bluesky/raw"
}

variable "athena_results_prefix" {
  description = "Outside `raw_prefix`, so Iceberg orphan cleanup never sees it."
  default     = "athena-results/backfill"
}

variable "backfill_start_month" {
  description = "Month of `BLUESKY_START_DATE` in `bluesky_backfill_app/constants.py`."
  default     = "2022-11-01"
}

variable "backfill_end_date" {
  description = "`DATA_END_DATE` in `bluesky_backfill_app/constants.py`, inclusive."
  default     = "2026-08-07"
}

variable "backfill_chunk_months" {
  description = "Months per statement. Tables are partitioned by day and Athena writes at most 100 partitions per statement."
  default     = 3

  validation {
    condition     = var.backfill_chunk_months >= 1 && var.backfill_chunk_months <= 3
    error_message = "4 months can exceed 100 days."
  }
}

locals {
  backfill_start_year    = tonumber(split("-", var.backfill_start_month)[0])
  backfill_start_index   = tonumber(split("-", var.backfill_start_month)[1]) - 1
  backfill_end_exclusive = formatdate("YYYY-MM-DD", timeadd("${var.backfill_end_date}T00:00:00Z", "24h"))
  backfill_month_count = (
    (tonumber(split("-", var.backfill_end_date)[0]) - local.backfill_start_year) * 12
    + tonumber(split("-", var.backfill_end_date)[1]) - 1 - local.backfill_start_index + 1
  )

  backfill_chunk_bounds = [
    for i in range(0, local.backfill_month_count, var.backfill_chunk_months) : {
      start = format("%04d-%02d-01", local.backfill_start_year + floor((local.backfill_start_index + i) / 12), (local.backfill_start_index + i) % 12 + 1)
      end   = format("%04d-%02d-01", local.backfill_start_year + floor((local.backfill_start_index + i + var.backfill_chunk_months) / 12), (local.backfill_start_index + i + var.backfill_chunk_months) % 12 + 1)
    }
  ]

  # [start, end) windows covering the backfill range. The last one stops at
  # `backfill_end_date` so maintenance never touches Jetstream-only days.
  backfill_chunks = [
    for c in local.backfill_chunk_bounds : {
      start = c.start
      end   = timecmp("${c.end}T00:00:00Z", "${local.backfill_end_exclusive}T00:00:00Z") > 0 ? local.backfill_end_exclusive : c.end
    }
  ]
}

data "aws_caller_identity" "current" {}

data "aws_sns_topic" "maintenance_alarms" {
  name = "${var.raw_glue_database}_maintenance_alarms"
}

resource "aws_athena_workgroup" "backfill" {
  name = "bluesky_backfill"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${var.s3_bucket}/${var.athena_results_prefix}/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

resource "aws_iam_role" "backfill_states" {
  name = "bluesky_backfill_states"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "backfill_states" {
  name = "bluesky_backfill_states"
  role = aws_iam_role.backfill_states.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:StopQueryExecution",
          "athena:GetWorkGroup",
          "athena:GetDataCatalog",
        ]
        Resource = [
          aws_athena_workgroup.backfill.arn,
          "arn:aws:athena:${var.aws_region}:${data.aws_caller_identity.current.account_id}:datacatalog/*",
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetDatabases",
          "glue:GetTable",
          "glue:GetTables",
          "glue:GetPartition",
          "glue:GetPartitions",
        ]
        Resource = [
          "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
          "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:database/${var.raw_glue_database}",
          "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.raw_glue_database}/*",
          "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:database/${var.landing_glue_database}",
          "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.landing_glue_database}/*",
        ]
      },
      {
        # Iceberg commits swap the table's metadata pointer. Landing is read-only.
        Effect = "Allow"
        Action = ["glue:UpdateTable"]
        Resource = [
          "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
          "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:database/${var.raw_glue_database}",
          "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.raw_glue_database}/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetBucketLocation", "s3:ListBucket"]
        Resource = "arn:aws:s3:::${var.s3_bucket}"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "arn:aws:s3:::${var.s3_bucket}/${var.landing_prefix}/*"
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]
        Resource = [
          "arn:aws:s3:::${var.s3_bucket}/${var.raw_prefix}/*",
          "arn:aws:s3:::${var.s3_bucket}/${var.athena_results_prefix}/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem"]
        Resource = aws_dynamodb_table.merge_cursor.arn
      },
    ]
  })
}

resource "aws_iam_role" "backfill_scheduler" {
  name = "bluesky_backfill_scheduler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "backfill_scheduler" {
  name = "bluesky_backfill_scheduler"
  role = aws_iam_role.backfill_scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "states:StartExecution"
      Resource = [aws_sfn_state_machine.merge.arn, aws_sfn_state_machine.maintenance.arn]
    }]
  })
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "did_table_name" {
  value = aws_dynamodb_table.backfill_dids.name
}

output "cursor_table_name" {
  value = aws_dynamodb_table.backfill_cursor.name
}

output "queue_url" {
  value = aws_sqs_queue.backfill_dids.url
}

output "dlq_url" {
  value = aws_sqs_queue.backfill_dids_dlq.url
}
