# ---------------------------------------------------------------------------
# Landing -> Iceberg merge
#
# Weekly. For each record type, copy each landing day in (merged_through,
# window] once into a Hive table partitioned by month of created_at, then
# INSERT one month at a time into `bluesky_raw`. Landing files are partitioned
# only by dt, so a created_at predicate does not reduce the bytes scanned.
# One INSERT per month re-read that dt window (46 times on the backfill range).
#
# The month split stays. Athena writes at most 100 partitions per INSERT, and
# `bluesky_raw` is partitioned by day, so one INSERT of the whole range
# (~1,360 days) fails with ICEBERG_TOO_MANY_OPEN_PARTITIONS. A quarter of
# likes is also near Athena's memory limit. The stage copy does not sort.
# The Iceberg INSERT dedupes one chunk of the stage. The stage name includes
# the execution name, so one run cannot drop another's files. Two overlapping
# runs can still both insert; the single cursor already allowed that.
# A landing day writes at most one Hive partition per month, under the cap.
#
# The scheduled runs on 2026-10-18, 2026-10-25, and 2026-11-01 failed after
# about 22 minutes with "Query exhausted resources at this scale factor".
# The created_at predicate was outside row_number(), so each likes statement
# sorted the whole dt window. The first likes quarter (map index 16) is what
# failed. Moving that predicate inside the window and chunking by month,
# rather than by quarter, is what let the 2026-11-02 catch-up finish.
#
# Cursor. `merged_through` is still the last fully merged dt, inclusive.
# A run also stores `pending_through` and a string set `completed` of
# `record_type|chunk_start` for months that committed. A failed run does not
# move `merged_through`. The next run finishes that same window and skips
# months already in `completed`, then merges any later days through
# yesterday. Two successful windows can still both contain a uri;
# `dedup_backfill` is the cleanup, same as before.
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
  # Under athena-results/backfill/, which already expires after 7 days.
  # The bucket has one lifecycle configuration, in the Jetstream root.
  merge_stage_root = "${var.athena_results_prefix}/merge-stage"
  # Includes ICEBERG_COMMIT_ERROR. A failed INSERT commits nothing.
  merge_athena_retry = [
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
  # `{day}` is filled by the state machine. One landing day, so the created_at
  # filter is not what limits the scan; dt is.
  merge_plans = [
    for record_type, columns in local.landing_columns : {
      record_type = record_type
      # `{exec}` is this execution's name, sanitized. Two runs do not share a stage.
      stage_prefix = "${local.merge_stage_root}/{exec}/${record_type}/"
      drop_sql     = "DROP TABLE IF EXISTS ${var.landing_glue_database}.merge_stage_${record_type}_{exec}"
      create_sql = join(" ", [
        "CREATE EXTERNAL TABLE ${var.landing_glue_database}.merge_stage_${record_type}_{exec} (",
        join(", ", [for column in columns : "${column.name} ${column.type}"]),
        ") PARTITIONED BY (created_month string) STORED AS PARQUET",
        "LOCATION 's3://${var.s3_bucket}/${local.merge_stage_root}/{exec}/${record_type}/'",
      ])
      day_sql = join(" ", [
        "INSERT INTO ${var.landing_glue_database}.merge_stage_${record_type}_{exec}",
        "SELECT ${join(", ", columns[*].name)}, date_format(created_at, '%Y-%m')",
        "FROM ${var.landing_glue_database}.${record_type}",
        "WHERE dt = '{day}'",
        "AND created_at >= timestamp '${var.backfill_start_month} 00:00:00'",
        "AND created_at < timestamp '${local.backfill_end_exclusive} 00:00:00'",
      ])
      chunks = [
        for chunk in local.backfill_chunks : {
          key = "${record_type}|${chunk.start}"
          sql = join(" ", [
            "INSERT INTO ${var.raw_glue_database}.${record_type} (${join(", ", columns[*].name)})",
            "SELECT ${join(", ", columns[*].name)} FROM (",
            "SELECT *, row_number() OVER (PARTITION BY uri ORDER BY rev DESC, ingested_at DESC) AS rn",
            "FROM ${var.landing_glue_database}.merge_stage_${record_type}_{exec}",
            # Inclusive month of the last day in the chunk. A 2- or 3-month
            # chunk must read every stage partition it covers.
            "WHERE created_month >= '${substr(chunk.start, 0, 7)}'",
            "AND created_month <= '${substr(formatdate("YYYY-MM-DD", timeadd("${chunk.end}T00:00:00Z", "-24h")), 0, 7)}'",
            "AND created_at >= timestamp '${chunk.start} 00:00:00'",
            "AND created_at < timestamp '${chunk.end} 00:00:00'",
            ") WHERE rn = 1",
          ])
        }
      ]
    }
  ]
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

  lifecycle {
    precondition {
      condition     = length(local.backfill_chunks) <= 100
      error_message = "Each landing day is written into one stage partition per created_at month. Athena allows 100 partitions per INSERT."
    }
  }

  definition = jsonencode({
    Comment       = "Append new landing days into ${var.raw_glue_database}"
    QueryLanguage = "JSONata"
    # Max time for the whole run, all four tables.
    TimeoutSeconds = 86400
    StartAt        = "GetCursor"
    States = {
      # `yesterday` is fixed here so a run that crosses midnight UTC does not
      # change the window it already started.
      GetCursor = {
        Type     = "Task"
        Resource = "arn:aws:states:::dynamodb:getItem"
        Arguments = {
          TableName      = aws_dynamodb_table.merge_cursor.name
          Key            = { id = { S = "merge" } }
          ConsistentRead = true
        }
        Assign = {
          yesterday       = "{% $fromMillis($millis() - 86400000, '[Y0001]-[M01]-[D01]') %}"
          merged_through  = "{% $exists($states.result.Item.merged_through) ? $states.result.Item.merged_through.S : '' %}"
          pending_through = "{% $exists($states.result.Item.pending_through) ? $states.result.Item.pending_through.S : '' %}"
          completed       = "{% $exists($states.result.Item.completed) ? $states.result.Item.completed.SS : [] %}"
          exec_id         = "{% $lowercase($replace($states.context.Execution.Name, /[^A-Za-z0-9]/, '_')) %}"
        }
        Next = "CheckCursor"
      }

      CheckCursor = {
        Type = "Choice"
        Choices = [
          { Condition = "{% $merged_through = '' %}", Next = "CursorMissing" },
          # Finish the window a previous attempt started, including its
          # completed months, even if yesterday has moved on.
          { Condition = "{% $pending_through != '' and $pending_through > $merged_through %}", Next = "ResumeWindow" },
          { Condition = "{% $yesterday <= $merged_through %}", Next = "UpToDate" },
        ]
        Default = "StartWindow"
      }

      StartWindow = {
        Type     = "Task"
        Resource = "arn:aws:states:::dynamodb:updateItem"
        Arguments = {
          TableName        = aws_dynamodb_table.merge_cursor.name
          Key              = { id = { S = "merge" } }
          UpdateExpression = "SET pending_through = :through REMOVE completed"
          ExpressionAttributeValues = {
            ":through" = { S = "{% $yesterday %}" }
          }
        }
        Next = "BeginMerge"
      }

      BeginMerge = {
        Type = "Pass"
        Assign = {
          through   = "{% $yesterday %}"
          completed = []
        }
        Next = "Merge"
      }

      ResumeWindow = {
        Type = "Pass"
        Assign = {
          through = "{% $pending_through %}"
        }
        Next = "Merge"
      }

      # One table at a time. Variables are execution-scoped, and two tables
      # would overwrite each other's stage SQL. Iceberg commits are serial too.
      Merge = {
        Type           = "Map"
        Items          = local.merge_plans
        MaxConcurrency = 1
        ItemProcessor = {
          ProcessorConfig = { Mode = "INLINE" }
          StartAt         = "AssignTable"
          States = {
            AssignTable = {
              Type = "Pass"
              Assign = {
                record_type  = "{% $states.input.record_type %}"
                stage_prefix = "{% $replace($states.input.stage_prefix, '{exec}', $exec_id) %}"
                drop_sql     = "{% $replace($states.input.drop_sql, '{exec}', $exec_id) %}"
                create_sql   = "{% $replace($states.input.create_sql, '{exec}', $exec_id) %}"
                day_sql      = "{% $replace($states.input.day_sql, '{exec}', $exec_id) %}"
                chunks       = "{% [$states.input.chunks.{\"key\": key, \"sql\": $replace(sql, '{exec}', $exec_id)}] %}"
                chunk_index  = 0
                day          = "{% $fromMillis($toMillis($merged_through & 'T00:00:00.000Z') + 86400000, '[Y0001]-[M01]-[D01]') %}"
              }
              Next = "DropBefore"
            }

            DropBefore = {
              Type     = "Task"
              Resource = "arn:aws:states:::athena:startQueryExecution.sync"
              Arguments = {
                QueryString = "{% $drop_sql %}"
                WorkGroup   = aws_athena_workgroup.backfill.name
              }
              Retry  = local.merge_athena_retry
              Output = {}
              Next   = "ListBefore"
            }

            ListBefore = {
              Type     = "Task"
              Resource = "arn:aws:states:::aws-sdk:s3:listObjectsV2"
              Arguments = {
                Bucket  = var.s3_bucket
                Prefix  = "{% $stage_prefix %}"
                MaxKeys = 100
              }
              Next = "DeleteChoiceBefore"
            }

            DeleteChoiceBefore = {
              Type = "Choice"
              Choices = [
                {
                  Condition = "{% $exists($states.input.Contents) and $count($states.input.Contents) > 0 %}"
                  Next      = "DeleteBefore"
                },
              ]
              Default = "CheckTableDone"
            }

            DeleteBefore = {
              Type     = "Task"
              Resource = "arn:aws:states:::aws-sdk:s3:deleteObjects"
              Arguments = {
                Bucket = var.s3_bucket
                Delete = {
                  Objects = "{% [$states.input.Contents.{\"Key\": Key}] %}"
                }
              }
              Next = "ListBefore"
            }

            # Months already committed for this window. Drop the leftover
            # stage, then move on. A retry must not insert those months again.
            CheckTableDone = {
              Type = "Choice"
              Choices = [
                {
                  Condition = "{% $count($completed[$substring($, 0, $length($record_type & '|')) = ($record_type & '|')]) = $count($chunks) %}"
                  Next      = "TableDone"
                },
              ]
              Default = "CreateStage"
            }

            CreateStage = {
              Type     = "Task"
              Resource = "arn:aws:states:::athena:startQueryExecution.sync"
              Arguments = {
                QueryString = "{% $create_sql %}"
                WorkGroup   = aws_athena_workgroup.backfill.name
              }
              Retry  = local.merge_athena_retry
              Output = {}
              Next   = "DayChoice"
            }

            DayChoice = {
              Type = "Choice"
              Choices = [
                { Condition = "{% $day <= $through %}", Next = "StageDay" },
              ]
              Default = "ChunkChoice"
            }

            StageDay = {
              Type     = "Task"
              Resource = "arn:aws:states:::athena:startQueryExecution.sync"
              Arguments = {
                QueryString = "{% $replace($day_sql, '{day}', $day) %}"
                WorkGroup   = aws_athena_workgroup.backfill.name
              }
              Retry  = local.merge_athena_retry
              Output = {}
              Next   = "AdvanceDay"
            }

            AdvanceDay = {
              Type = "Pass"
              Assign = {
                day = "{% $fromMillis($toMillis($day & 'T00:00:00.000Z') + 86400000, '[Y0001]-[M01]-[D01]') %}"
              }
              Next = "DayChoice"
            }

            ChunkChoice = {
              Type = "Choice"
              Choices = [
                { Condition = "{% $chunk_index < $count($chunks) %}", Next = "MaybeInsert" },
              ]
              Default = "DropAfter"
            }

            MaybeInsert = {
              Type = "Choice"
              Choices = [
                { Condition = "{% $chunks[$chunk_index].key in $completed %}", Next = "AdvanceChunk" },
              ]
              Default = "RunInsert"
            }

            RunInsert = {
              Type     = "Task"
              Resource = "arn:aws:states:::athena:startQueryExecution.sync"
              Arguments = {
                QueryString = "{% $chunks[$chunk_index].sql %}"
                WorkGroup   = aws_athena_workgroup.backfill.name
              }
              Retry  = local.merge_athena_retry
              Output = {}
              Next   = "RecordChunk"
            }

            RecordChunk = {
              Type     = "Task"
              Resource = "arn:aws:states:::dynamodb:updateItem"
              Arguments = {
                TableName        = aws_dynamodb_table.merge_cursor.name
                Key              = { id = { S = "merge" } }
                UpdateExpression = "ADD completed :chunk"
                ExpressionAttributeValues = {
                  ":chunk" = { SS = ["{% $chunks[$chunk_index].key %}"] }
                }
              }
              Next = "AdvanceChunk"
            }

            AdvanceChunk = {
              Type = "Pass"
              Assign = {
                chunk_index = "{% $chunk_index + 1 %}"
              }
              Next = "ChunkChoice"
            }

            DropAfter = {
              Type     = "Task"
              Resource = "arn:aws:states:::athena:startQueryExecution.sync"
              Arguments = {
                QueryString = "{% $drop_sql %}"
                WorkGroup   = aws_athena_workgroup.backfill.name
              }
              Retry  = local.merge_athena_retry
              Output = {}
              Next   = "ListAfter"
            }

            ListAfter = {
              Type     = "Task"
              Resource = "arn:aws:states:::aws-sdk:s3:listObjectsV2"
              Arguments = {
                Bucket  = var.s3_bucket
                Prefix  = "{% $stage_prefix %}"
                MaxKeys = 100
              }
              Next = "DeleteChoiceAfter"
            }

            DeleteChoiceAfter = {
              Type = "Choice"
              Choices = [
                {
                  Condition = "{% $exists($states.input.Contents) and $count($states.input.Contents) > 0 %}"
                  Next      = "DeleteAfter"
                },
              ]
              Default = "TableDone"
            }

            DeleteAfter = {
              Type     = "Task"
              Resource = "arn:aws:states:::aws-sdk:s3:deleteObjects"
              Arguments = {
                Bucket = var.s3_bucket
                Delete = {
                  Objects = "{% [$states.input.Contents.{\"Key\": Key}] %}"
                }
              }
              Next = "ListAfter"
            }

            TableDone = {
              Type = "Pass"
              End  = true
            }
          }
        }
        Output = {}
        Next   = "PutCursor"
      }

      # Replaces the item, which drops pending_through and completed.
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
        Next = "MaybeContinue"
      }

      # A resumed window can end before yesterday. Merge the gap in this run.
      MaybeContinue = {
        Type = "Choice"
        Choices = [
          { Condition = "{% $yesterday > $through %}", Next = "GetCursor" },
        ]
        Default = "UpToDate"
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
