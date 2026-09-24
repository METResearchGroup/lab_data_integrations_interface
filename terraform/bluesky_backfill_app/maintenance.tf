# ---------------------------------------------------------------------------
# Backfill maintenance
#
#   optimize_backfill  Bin-packs the backfill range. Jetstream's `optimize_full`
#                      starts at 2026-08-01, so nothing else compacts the
#                      partitions the merge writes into.
#
#   dedup_backfill     Masks cross-file duplicate URIs over the backfill range,
#                      same DELETE as Jetstream's weekly `dedup`. Catches copies
#                      from separate merge runs and from reruns. Merge-on-read:
#                      follow it with `optimize_backfill` to fold the deletes in.
#
# One statement per table per chunk, for the 100-partition cap.
# ---------------------------------------------------------------------------

locals {
  backfill_chunk_predicates = [
    for chunk in local.backfill_chunks :
    "created_at >= timestamp '${chunk.start} 00:00:00' AND created_at < timestamp '${chunk.end} 00:00:00'"
  ]

  optimize_backfill_statements = flatten([
    for record_type in keys(local.landing_columns) : [
      for predicate in local.backfill_chunk_predicates :
      "OPTIMIZE ${var.raw_glue_database}.${record_type} REWRITE DATA USING BIN_PACK WHERE ${predicate}"
    ]
  ])

  # Cross-file duplicates only; mirrors `dedup_sql` in
  # `terraform/bluesky_ingestion_jetstream/maintenance.tf`.
  dedup_backfill_statements = flatten([
    for record_type in keys(local.landing_columns) : [
      for predicate in local.backfill_chunk_predicates : join(" ", [
        "DELETE FROM ${var.raw_glue_database}.${record_type}",
        "WHERE ${predicate}",
        "AND (uri, \"$path\") IN (",
        "SELECT uri, p FROM (",
        "SELECT uri, \"$path\" AS p,",
        "row_number() OVER (PARTITION BY uri ORDER BY \"$path\") AS rn",
        "FROM ${var.raw_glue_database}.${record_type}",
        "WHERE ${predicate}",
        ") WHERE rn > 1)",
      ])
    ]
  ])
}

resource "aws_sfn_state_machine" "maintenance" {
  name     = "bluesky_backfill_maintenance"
  role_arn = aws_iam_role.backfill_states.arn

  definition = jsonencode({
    Comment       = "OPTIMIZE and dedup over the backfill range of ${var.raw_glue_database}"
    QueryLanguage = "JSONata"
    # Max time for the whole run, all four tables.
    TimeoutSeconds = 86400
    StartAt        = "SelectJob"
    States = {
      SelectJob = {
        Type = "Choice"
        Choices = [
          { Condition = "{% $states.input.job = 'optimize_backfill' %}", Next = "OptimizeBackfill" },
          { Condition = "{% $states.input.job = 'dedup_backfill' %}", Next = "DedupBackfill" },
        ]
        Default = "UnknownJob"
      }

      OptimizeBackfill = {
        Type   = "Pass"
        Assign = { statements = local.optimize_backfill_statements }
        Next   = "RunStatements"
      }

      DedupBackfill = {
        Type   = "Pass"
        Assign = { statements = local.dedup_backfill_statements }
        Next   = "RunStatements"
      }

      # Serial: statements on the same table would race on the Iceberg commit.
      RunStatements = {
        Type           = "Map"
        Items          = "{% $statements %}"
        MaxConcurrency = 1
        ItemProcessor = {
          ProcessorConfig = { Mode = "INLINE" }
          StartAt         = "RunStatement"
          States = {
            RunStatement = {
              Type     = "Task"
              Resource = "arn:aws:states:::athena:startQueryExecution.sync"
              Arguments = {
                QueryString = "{% $states.input %}"
                WorkGroup   = aws_athena_workgroup.backfill.name
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
              Output = {}
              End    = true
            }
          }
        }
        Output = {}
        End    = true
      }

      UnknownJob = {
        Type  = "Fail"
        Error = "UnknownJob"
        Cause = "Input `job` must be one of: optimize_backfill, dedup_backfill."
      }
    }
  })
}

# `dedup_backfill` has no schedule: run it on demand, then `optimize_backfill`.
resource "aws_scheduler_schedule" "optimize_backfill" {
  name                         = "bluesky_backfill_optimize"
  description                  = "Bin-pack the backfill range of ${var.raw_glue_database}."
  schedule_expression          = "cron(0 7 1 * ? *)"
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.maintenance.arn
    role_arn = aws_iam_role.backfill_scheduler.arn
    input    = jsonencode({ job = "optimize_backfill" })

    # The next month's run picks up whatever this one missed.
    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "maintenance_failed" {
  alarm_name          = "bluesky_backfill_maintenance_failed"
  alarm_description   = "A backfill maintenance execution failed."
  namespace           = "AWS/States"
  metric_name         = "ExecutionsFailed"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.maintenance.arn
  }

  alarm_actions = [data.aws_sns_topic.maintenance_alarms.arn]
}

# A timed-out execution is not counted in ExecutionsFailed.
resource "aws_cloudwatch_metric_alarm" "maintenance_timed_out" {
  alarm_name          = "bluesky_backfill_maintenance_timed_out"
  alarm_description   = "A backfill maintenance execution ran past its 1-day timeout."
  namespace           = "AWS/States"
  metric_name         = "ExecutionsTimedOut"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.maintenance.arn
  }

  alarm_actions = [data.aws_sns_topic.maintenance_alarms.arn]
}

output "maintenance_state_machine_arn" {
  description = <<-EOT
    `aws stepfunctions start-execution --state-machine-arn <this> --input '{"job":"<job>"}'`
    where <job> is optimize_backfill or dedup_backfill.
  EOT
  value       = aws_sfn_state_machine.maintenance.arn
}
