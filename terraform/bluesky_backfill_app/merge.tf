# ---------------------------------------------------------------------------
# Landing -> Iceberg merge
#
# Weekly. Appends every landing day in (merged_through, yesterday] into
# `bluesky_raw`, one INSERT per record type per chunk, then advances the
# cursor. Duplicates are removed within a run only.
#
# A failed run leaves the cursor alone; rerunning re-inserts the chunks that
# had succeeded. `dedup_range` cleans those up.
# ---------------------------------------------------------------------------

variable "merge_cursor_table" {
  description = "Not read by Python; only the merge state machine uses it."
  default     = "bluesky_backfill_merge_cursor"
}

variable "merge_cursor_seed" {
  description = "Day before the first landing `dt`. Only applied on create."
  default     = "2026-09-14"
}

locals {
  # Filled at run time. `{merged_through}` is exclusive, `{through}` inclusive.
  merge_statements = flatten([
    for record_type, columns in local.landing_columns : [
      for chunk in local.backfill_chunks : join(" ", [
        "INSERT INTO ${var.raw_glue_database}.${record_type} (${join(", ", columns[*].name)})",
        "SELECT ${join(", ", columns[*].name)} FROM (",
        "SELECT *, row_number() OVER (PARTITION BY uri ORDER BY rev DESC, ingested_at DESC) AS rn",
        "FROM ${var.landing_glue_database}.${record_type}",
        "WHERE dt > '{merged_through}' AND dt <= '{through}'",
        ") WHERE rn = 1",
        "AND created_at >= timestamp '${chunk.start} 00:00:00'",
        "AND created_at < timestamp '${chunk.end} 00:00:00'",
      ])
    ]
  ])
}

resource "aws_dynamodb_table" "merge_cursor" {
  name         = var.merge_cursor_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# A missing item fails the run rather than merging everything.
resource "aws_dynamodb_table_item" "merge_cursor" {
  table_name = aws_dynamodb_table.merge_cursor.name
  hash_key   = aws_dynamodb_table.merge_cursor.hash_key

  item = jsonencode({
    id             = { S = "merge" }
    merged_through = { S = var.merge_cursor_seed }
  })

  # The state machine owns the value after creation.
  lifecycle {
    ignore_changes = [item]
  }
}

resource "aws_sfn_state_machine" "merge" {
  name     = "bluesky_backfill_merge"
  role_arn = aws_iam_role.backfill_states.arn

  definition = jsonencode({
    Comment       = "Append new landing days into ${var.raw_glue_database}"
    QueryLanguage = "JSONata"
    # Max time for the whole run, all four tables.
    TimeoutSeconds = 86400
    StartAt        = "GetCursor"
    States = {
      # `through` is fixed here so every statement and the cursor agree, even
      # if the run crosses midnight UTC.
      GetCursor = {
        Type     = "Task"
        Resource = "arn:aws:states:::dynamodb:getItem"
        Arguments = {
          TableName      = aws_dynamodb_table.merge_cursor.name
          Key            = { id = { S = "merge" } }
          ConsistentRead = true
        }
        Assign = {
          through        = "{% $fromMillis($millis() - 86400000, '[Y0001]-[M01]-[D01]') %}"
          merged_through = "{% $exists($states.result.Item) ? $states.result.Item.merged_through.S : '' %}"
        }
        Next = "CheckCursor"
      }

      CheckCursor = {
        Type = "Choice"
        Choices = [
          { Condition = "{% $merged_through = '' %}", Next = "CursorMissing" },
          { Condition = "{% $merged_through >= $through %}", Next = "UpToDate" },
        ]
        Default = "Merge"
      }

      # Serial: statements on the same table would race on the Iceberg commit.
      Merge = {
        Type           = "Map"
        Items          = local.merge_statements
        MaxConcurrency = 1
        ItemProcessor = {
          ProcessorConfig = { Mode = "INLINE" }
          StartAt         = "RunInsert"
          States = {
            RunInsert = {
              Type     = "Task"
              Resource = "arn:aws:states:::athena:startQueryExecution.sync"
              Arguments = {
                QueryString = "{% $replace($replace($states.input, '{merged_through}', $merged_through), '{through}', $through) %}"
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
                  # Includes ICEBERG_COMMIT_ERROR. A failed INSERT commits nothing.
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
        Next   = "PutCursor"
      }

      PutCursor = {
        Type     = "Task"
        Resource = "arn:aws:states:::dynamodb:putItem"
        Arguments = {
          TableName = aws_dynamodb_table.merge_cursor.name
          Item = {
            id             = { S = "merge" }
            merged_through = { S = "{% $through %}" }
          }
        }
        End = true
      }

      UpToDate = { Type = "Succeed" }

      CursorMissing = {
        Type  = "Fail"
        Error = "MergeCursorMissing"
        Cause = "No `merge` item in ${var.merge_cursor_table}. Seed it rather than merging from the beginning."
      }
    }
  })
}

# Sundays, after the 05:00 VACUUM and outside the 03:00-06:00 maintenance window.
resource "aws_scheduler_schedule" "merge" {
  name                         = "bluesky_backfill_merge"
  description                  = "Append new landing days into ${var.raw_glue_database}."
  schedule_expression          = "cron(0 9 ? * SUN *)"
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.merge.arn
    role_arn = aws_iam_role.backfill_scheduler.arn
    input    = jsonencode({})

    # The next run picks up whatever this one missed.
    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "merge_failed" {
  alarm_name          = "bluesky_backfill_merge_failed"
  alarm_description   = "A backfill merge execution failed. The cursor did not advance."
  namespace           = "AWS/States"
  metric_name         = "ExecutionsFailed"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.merge.arn
  }

  alarm_actions = [data.aws_sns_topic.maintenance_alarms.arn]
}

# A timed-out execution is not counted in ExecutionsFailed.
resource "aws_cloudwatch_metric_alarm" "merge_timed_out" {
  alarm_name          = "bluesky_backfill_merge_timed_out"
  alarm_description   = "A backfill merge ran past its 1-day timeout. The cursor did not advance."
  namespace           = "AWS/States"
  metric_name         = "ExecutionsTimedOut"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.merge.arn
  }

  alarm_actions = [data.aws_sns_topic.maintenance_alarms.arn]
}

# Catches runs that never start (schedule disabled, scheduler errors), which
# `merge_failed` cannot see. Days with no execution are missing data, so they
# count as breaching. 7 days is the CloudWatch maximum for an alarm's window.
resource "aws_cloudwatch_metric_alarm" "merge_stale" {
  alarm_name          = "bluesky_backfill_merge_stale"
  alarm_description   = "No successful backfill merge in 7 days. Landing files expire after 30."
  namespace           = "AWS/States"
  metric_name         = "ExecutionsSucceeded"
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 7
  datapoints_to_alarm = 7
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.merge.arn
  }

  alarm_actions = [data.aws_sns_topic.maintenance_alarms.arn]
}

output "merge_state_machine_arn" {
  description = <<-EOT
    Run on demand, same as the schedule:
    `aws stepfunctions start-execution --state-machine-arn <this> --input '{}'`
  EOT
  value       = aws_sfn_state_machine.merge.arn
}
