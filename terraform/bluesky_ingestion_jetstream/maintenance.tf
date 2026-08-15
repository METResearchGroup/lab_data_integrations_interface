# ---------------------------------------------------------------------------
# Iceberg table maintenance
#
#   OPTIMIZE  bin-packs a partition's small files into large ones. Scoped to a
#             trailing window of closed days.
#              
#   VACUUM    expires snapshots past a retention age, then deletes the data
#             files, manifests, and manifest lists that no surviving snapshot
#             references.
# ---------------------------------------------------------------------------

variable "athena_results_prefix" {
  description = <<-EOT
    Where Athena writes query output. Deliberately a sibling of `s3_prefix`
    rather than a child: orphan cleanup treats anything under the warehouse
    root as deletable if no snapshot references it, and query results are
    unreferenced by definition. Same reasoning as `DEAD_LETTER_PREFIX` in
    `bluesky_ingestion_jetstream/aws/constants.py`.
  EOT
  default     = "athena-results/maintenance"
}

variable "athena_results_retention_days" {
  description = <<-EOT
    Query output is a few hundred bytes of "rows rewritten" and is never read
    twice, so this only needs to outlive a debugging session.
  EOT
  default     = 7
}

variable "record_types" {
  description = "One Iceberg table each. Mirrors `RECORD_TYPES` in `bluesky_ingestion_jetstream/constants.py`."
  type        = list(string)
  default     = ["posts", "likes", "reposts", "follows"]
}

variable "optimize_lookback_days" {
  description = <<-EOT
    How many closed days the daily OPTIMIZE reconsiders. Beyond the first, days
    are near-free: bin-pack skips a partition holding fewer than
    `min-input-files` (5) candidates, so an already-compacted day is a metadata
    check. The margin is there to catch late arrivals.
  EOT
  default     = 3
}

variable "optimize_full_start_month" {
  description = <<-EOT
    First month `optimize_full` covers, as `YYYY-MM-DD`. Earlier partitions are
    left alone: they predate `MAX_CREATED_AT_BACKDATE` in
    `bluesky_ingestion_jetstream/constants.py`, so they hold a few KB of client
    clock junk that compaction cannot meaningfully shrink.
  EOT
  default     = "2026-08-01"
}

locals {
  optimize_full_start_year  = tonumber(split("-", var.optimize_full_start_month)[0])
  optimize_full_start_index = tonumber(split("-", var.optimize_full_start_month)[1])

  # Athena caps OPTIMIZE at 100 partitions per statement, so an unbounded rewrite
  # fails outright once a table holds more days than that. One statement per month
  # keeps each under ~31.
  #
  # The list runs from `optimize_full_start_month` through whichever month the
  # execution lands in, computed by the state machine rather than at apply time so
  # a new month needs no `terraform apply`.
  #
  # The outer `[...]` is load-bearing: JSONata collapses a single-element sequence
  # to a scalar, and the first month of a fresh start date is exactly that case.
  optimize_full_predicates = join(" ", [
    "{% [$map($range(0, ($number($now(\"[Y0001]\")) - ${local.optimize_full_start_year}) * 12",
    "+ $number($now(\"[M]\")) - ${local.optimize_full_start_index}, 1), function($i) {",
    "\"WHERE created_at >= date '${var.optimize_full_start_month}' + interval '\" & $string($i) & \"' month",
    "AND created_at < date '${var.optimize_full_start_month}' + interval '\" & $string($i + 1) & \"' month\" })] %}",
  ])
}

# ---------------------------------------------------------------------------
# Athena workgroup
#
# Its own workgroup since Athena publishes CloudWatch metrics per workgroup
# ---------------------------------------------------------------------------

resource "aws_athena_workgroup" "maintenance" {
  name = "${var.glue_database}_maintenance"

  configuration {
    enforce_workgroup_configuration = true

    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.warehouse.bucket}/${var.athena_results_prefix}/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

# ---------------------------------------------------------------------------
# Results lifecycle
#
# Cleanup for failed OPTIMIZE Athena operations
# ---------------------------------------------------------------------------

resource "aws_s3_bucket_lifecycle_configuration" "warehouse" {
  bucket = aws_s3_bucket.warehouse.id

  rule {
    id     = "expire-athena-maintenance-results"
    status = "Enabled"

    filter {
      prefix = "${var.athena_results_prefix}/"
    }

    expiration {
      days = var.athena_results_retention_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

# ---------------------------------------------------------------------------
# Execution role
#
# IAM role and permissions for Step Functions to run Athena OPTIMIZE and 
# VACUUM maintenance on Iceberg tables.
# ---------------------------------------------------------------------------

resource "aws_iam_role" "maintenance_states" {
  name = "${var.glue_database}_maintenance_states"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "maintenance_states" {
  name = "${var.glue_database}_maintenance_states"
  role = aws_iam_role.maintenance_states.id

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
          aws_athena_workgroup.maintenance.arn,
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
          "glue:UpdateTable",
          "glue:GetPartition",
          "glue:GetPartitions",
        ]
        Resource = [
          "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog",
          "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:database/${var.glue_database}",
          "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.glue_database}/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetBucketLocation", "s3:ListBucket"]
        Resource = aws_s3_bucket.warehouse.arn
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]
        Resource = [
          "${aws_s3_bucket.warehouse.arn}/${var.s3_prefix}/*",
          "${aws_s3_bucket.warehouse.arn}/${var.athena_results_prefix}/*",
        ]
      },
    ]
  })
}

data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------------------
# State machine
#
# AWS Step Function that orchestrates OPTIMIZE and VACUUM maintenance tasks 
# sequentially across all Iceberg tables.
# ---------------------------------------------------------------------------

resource "aws_sfn_state_machine" "maintenance" {
  name     = "${var.glue_database}_maintenance"
  role_arn = aws_iam_role.maintenance_states.arn

  definition = jsonencode({
    Comment = "Iceberg OPTIMIZE and VACUUM for ${var.glue_database}"
    StartAt = "SelectJob"
    States = {
      SelectJob = {
        Type = "Choice"
        Choices = [
          { Variable = "$.job", StringEquals = "optimize", Next = "OptimizeWindow" },
          { Variable = "$.job", StringEquals = "optimize_full", Next = "OptimizeFull" },
          { Variable = "$.job", StringEquals = "vacuum", Next = "Vacuum" },
        ]
        Default = "UnknownJob"
      }

      # Every job fans out over tables x predicates. `optimize` and `vacuum` carry a
      # single predicate; `optimize_full` carries one per month.
      OptimizeWindow = {
        Type = "Pass"
        Parameters = {
          tables       = var.record_types
          sql_template = "OPTIMIZE ${var.glue_database}.{} REWRITE DATA USING BIN_PACK {}"
          predicates = [
            "WHERE created_at >= current_date - interval '${var.optimize_lookback_days}' day AND created_at < current_date",
          ]
        }
        Next = "PerTable"
      }

      OptimizeFull = {
        Type          = "Pass"
        QueryLanguage = "JSONata"
        Output = {
          tables       = var.record_types
          sql_template = "OPTIMIZE ${var.glue_database}.{} REWRITE DATA USING BIN_PACK {}"
          predicates   = local.optimize_full_predicates
        }
        Next = "PerTable"
      }

      Vacuum = {
        Type = "Pass"
        Parameters = {
          tables       = var.record_types
          sql_template = "VACUUM ${var.glue_database}.{}{}"
          predicates   = [""]
        }
        Next = "PerTable"
      }

      PerTable = {
        Type           = "Map"
        ItemsPath      = "$.tables"
        MaxConcurrency = 1
        Parameters = {
          "table.$"        = "$$.Map.Item.Value"
          "sql_template.$" = "$.sql_template"
          "predicates.$"   = "$.predicates"
        }
        Iterator = {
          StartAt = "PerPredicate"
          States = {
            # Serial within a table: concurrent OPTIMIZEs race on the same Iceberg
            # commit and one of them loses.
            PerPredicate = {
              Type           = "Map"
              ItemsPath      = "$.predicates"
              MaxConcurrency = 1
              Parameters = {
                "predicate.$"    = "$$.Map.Item.Value"
                "table.$"        = "$.table"
                "sql_template.$" = "$.sql_template"
              }
              Iterator = {
                StartAt = "RunStatement"
                States = {
                  RunStatement = {
                    Type     = "Task"
                    Resource = "arn:aws:states:::athena:startQueryExecution.sync"
                    Parameters = {
                      "QueryString.$" = "States.Format($.sql_template, $.table, $.predicate)"
                      WorkGroup       = aws_athena_workgroup.maintenance.name
                    }
                    Retry = [
                      {
                        ErrorEquals     = ["Athena.TooManyRequestsException"]
                        IntervalSeconds = 30
                        MaxAttempts     = 4
                        BackoffRate     = 2
                      },
                      {
                        ErrorEquals     = ["States.TaskFailed"]
                        IntervalSeconds = 60
                        MaxAttempts     = 2
                        BackoffRate     = 2
                      },
                    ]
                    Catch = [{
                      ErrorEquals = ["States.ALL"]
                      Next        = "Failed"
                    }]
                    ResultPath = null
                    Next       = "Succeeded"
                  }
                  Succeeded = { Type = "Pass", Result = "ok", End = true }
                  Failed    = { Type = "Pass", Result = "failed", End = true }
                }
              }
              End = true
            }
          }
        }
        ResultPath = "$.results"
        Next       = "Summarize"
      }

      # Results nest one level per Map, and ASL has no array flatten, so the check
      # runs over the serialized form.
      Summarize = {
        Type = "Pass"
        Parameters = {
          "results.$" = "States.JsonToString($.results)"
        }
        Next = "CheckFailures"
      }

      CheckFailures = {
        Type = "Choice"
        Choices = [{
          Variable      = "$.results"
          StringMatches = "*failed*"
          Next          = "MaintenanceFailed"
        }]
        Default = "Done"
      }

      MaintenanceFailed = {
        Type  = "Fail"
        Error = "TableMaintenanceFailed"
        Cause = "One or more tables failed; see the Map iteration history for which."
      }

      UnknownJob = {
        Type  = "Fail"
        Error = "UnknownJob"
        Cause = "Input `job` must be one of: optimize, optimize_full, vacuum."
      }

      Done = { Type = "Succeed" }
    }
  })
}

# ---------------------------------------------------------------------------
# Schedules
#
# Amazon EventBridge Scheduler cron triggers for Iceberg table maintenance:
#
#   - OPTIMIZE (Daily @ 03:00 UTC)
#     Bin-packs small files for the rolling lookback window:
#     `created_at >= current_date - 3 days AND created_at < current_date`
#     Delayed until 03:00 to ensure yesterday's partition is fully closed.
#
#   - VACUUM (Sundays @ 05:00 UTC)
#     Expires snapshots older than 5 days and purges deleted S3 data files.
#     Scheduled post-optimization to sweep up the orphaned files it creates.
#
#   - OPTIMIZE_FULL (Saturdays @ 06:00 UTC)
#     Compaction back to `optimize_full_start_month`, one statement per month.
#     Catches stray small files in partitions the daily window cannot reach.
# ---------------------------------------------------------------------------

resource "aws_iam_role" "maintenance_scheduler" {
  name = "${var.glue_database}_maintenance_scheduler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "maintenance_scheduler" {
  name = "${var.glue_database}_maintenance_scheduler"
  role = aws_iam_role.maintenance_scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "states:StartExecution"
      Resource = aws_sfn_state_machine.maintenance.arn
    }]
  })
}

locals {
  maintenance_schedules = {
    optimize = {
      expression  = "cron(0 3 * * ? *)"
      description = "Bin-pack the last ${var.optimize_lookback_days} closed days."
    }
    vacuum = {
      expression  = "cron(0 5 ? * SUN *)"
      description = "Expire snapshots and delete what they orphaned."
    }
    optimize_full = {
      expression  = "cron(0 6 ? * SAT *)"
      description = "Unbounded compaction, for partitions the daily window cannot reach."
    }
  }
}

resource "aws_scheduler_schedule" "maintenance" {
  for_each = local.maintenance_schedules

  name                = "${var.glue_database}_${each.key}"
  description         = each.value.description
  schedule_expression = each.value.expression

  # UTC rather than a named zone: the partition transform is UTC, so a
  # DST-shifting local zone would move the window off the day boundary.
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.maintenance.arn
    role_arn = aws_iam_role.maintenance_scheduler.arn
    input    = jsonencode({ job = each.key })

    # A missed run is picked up by the next one, so no retries
    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}

# ---------------------------------------------------------------------------
# Alarm
#
# CloudWatch alarm and SNS topic that email alerts when an 
# Iceberg maintenance Step Function execution fails.
# ---------------------------------------------------------------------------

variable "maintenance_alarm_email" {
  description = "Optional. If set, subscribes this address to the alarm topic; AWS sends a confirmation mail that must be accepted."
  type        = string
  default     = ""
}

resource "aws_sns_topic" "maintenance_alarms" {
  name = "${var.glue_database}_maintenance_alarms"
}

resource "aws_sns_topic_subscription" "maintenance_alarms_email" {
  count = var.maintenance_alarm_email == "" ? 0 : 1

  topic_arn = aws_sns_topic.maintenance_alarms.arn
  protocol  = "email"
  endpoint  = var.maintenance_alarm_email
}

resource "aws_cloudwatch_metric_alarm" "maintenance_failed" {
  alarm_name          = "${var.glue_database}_maintenance_failed"
  alarm_description   = "A ${var.glue_database} OPTIMIZE or VACUUM execution failed."
  namespace           = "AWS/States"
  metric_name         = "ExecutionsFailed"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"

  treat_missing_data = "notBreaching"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.maintenance.arn
  }

  alarm_actions = [aws_sns_topic.maintenance_alarms.arn]
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "athena_workgroup_name" {
  value = aws_athena_workgroup.maintenance.name
}

output "maintenance_state_machine_arn" {
  description = <<-EOT
    Any job runs on demand, same as on its schedule:
    `aws stepfunctions start-execution --state-machine-arn <this> --input '{"job":"<job>"}'`
    where <job> is optimize, vacuum, or optimize_full.
  EOT
  value       = aws_sfn_state_machine.maintenance.arn
}

output "athena_results_uri" {
  value = "s3://${aws_s3_bucket.warehouse.bucket}/${var.athena_results_prefix}/"
}
