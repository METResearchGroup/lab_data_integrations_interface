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
