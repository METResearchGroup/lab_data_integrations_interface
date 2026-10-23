# Telemetry

[Overview](plan.md). Use Grafana Cloud. The OpenTelemetry wiring and the runbook already exist for the Python services on Railway, and the source notes say a Grafana MCP server is available to the agent. The repo does not configure that MCP server. Whether one is connected for this account is [not verified](plan.md#not-verified).

Sentry is optional. Skip it until the Grafana alerts below are in use.

Worker and container telemetry from Cloudflare is not on `main`. It depends on draft [PR #245](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/245). [PR #247](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/247) does not change the wrangler observability blocks.

## Where each signal should go

### Python services

`backend/` and `bluesky_ingestion_jetstream/` export traces, logs, and metrics when `OTEL_EXPORTER_OTLP_HEADERS` is set. `bluesky_backfill_app/telemetry/setup.py` wires metrics and logs only. On Railway the runbooks tell you to set the header per service. On the #245 Workers, `containerEnv` copies the same variable into the container when the Worker secret is non-empty. Set the secret on the API, Jetstream, and backfill Workers, or the containers export nothing.

### Workers

Export Worker logs and traces to Grafana Cloud, following [Export to Grafana Cloud](https://developers.cloudflare.com/workers/observability/exporting-opentelemetry-data/grafana-cloud/). Set `persist: false` on the destination so Cloudflare does not also store the same logs. The storage charge the notes are avoiding starts on 2026-12-01, documented at [OpenTelemetry export](https://developers.cloudflare.com/workers/observability/opentelemetry-export/) and on the [Workers Logs pricing](https://developers.cloudflare.com/workers/observability/logs/workers-logs/) page. #245 enables logs and traces at `head_sampling_rate` 1 and does not set a Grafana destination or `persist`.

### Container metrics

The Grafana log and trace export does not include Worker or container metrics. Poll the Cloudflare GraphQL Analytics API on a schedule. The container series include max and p95 memory in `containersMetricsAdaptiveGroups`, documented at [querying container metrics](https://developers.cloudflare.com/analytics/graphql-api/tutorials/querying-container-metrics/). The poll is new, and the repo does not contain it.

### AWS

Add a Grafana CloudWatch data source with a read-only role, documented at [the CloudWatch data source](https://grafana.com/docs/grafana-cloud/observe-and-act/connect-externally-hosted/data-sources/aws-cloudwatch/). API calls are billed by AWS. The Jetstream maintenance workgroup already sets `publish_cloudwatch_metrics_enabled = true`, so Athena `ProcessedBytes` for that workgroup can show up once the data source exists. The two workgroups in `terraform/data_platform/main.tf` do not publish CloudWatch metrics yet. Viewing the metrics is documented at [query metrics](https://docs.aws.amazon.com/athena/latest/ug/query-metrics-viewing.html).

### Uptime

Use Grafana Synthetic Monitoring HTTP checks, documented at [HTTP checks](https://grafana.com/docs/grafana-cloud/observe-and-act/testing/synthetic-monitoring/create-checks/checks/http/). The source notes cite a free tier of 100,000 checks a month. Check the UI, `GET /health`, and an authenticated `POST /query`. Whether Cloudflare Health Checks work on `workers.dev` is [not verified](plan.md#not-verified). Add the synthetic checks even if those Health Checks never work on `workers.dev`.

## Signals and alerts

Thresholds are starting points from the source notes. `$X` was left unset on purpose. Alert routes are in the next section.

| Surface | Signals to collect | Alert | Already in the repo |
| --- | --- | --- | --- |
| UI | Request rate, share of responses that are 5xx, p95 latency, and an authenticated synthetic check | 5xx above 2 percent for 5 minutes, or the synthetic check fails twice | No. The UI on `main` is the Vercel app. Worker logs exist only as a #245 preview config, and they stay in Cloudflare until the Grafana destination exists. |
| API | Request rate, errors, and latency per route. Supabase auth failures by reason | 5xx above 2 percent for 5 minutes. Auth failures above 20 percent of auth attempts over 15 minutes | FastAPI instrumentation in `backend/telemetry/setup.py` covers route spans when the OTel header is set. Auth rejection is a log line in `backend/auth.py`, not a counter by reason. |
| Jetstream | Events per minute by record type, cursor age, RSS, flush size, flush duration, S3 write failures, restarts | Cursor age above 10 minutes. RSS above 80 percent for 10 minutes. Any OOM restart. No S3 writes for 15 minutes | `bluesky_jetstream.cursor.timestamp`, `bluesky_jetstream.connected`, `bluesky_jetstream.rows.written`, `bluesky_jetstream.bytes.written`, connection failures, dead letters, and dropped rows. Flush size is on the byte counter and on the per-flush JSON log. Cursor age is the current time minus the timestamp, not its own series. RSS, flush duration, and OOM restarts are not exported. On Cloudflare, RSS and OOM come from the GraphQL container metrics, which #245 does not poll. |
| Backfill | Done count versus total in DynamoDB, queue depth, oldest message age, dead-letter count, and unmerged landing-zone files | Dead-letter count above 0. Oldest message age above 24 hours while a run is in progress. Merge cron failed or skipped | Gauges for buffer bytes, waiting messages (main queue and dead-letter queue), in-flight messages, and peak RSS. Counters for rows, bytes, repos landed, flush failures, and repo failures. No done-versus-total gauge, no oldest-message-age gauge, and no dashboard JSON. [Issue #165](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/165) asks for the dashboard and for merge-job health. Unmerged landing files and the merge cron depend on open [PR #220](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/220), which is not on `main`. |
| Search pipeline | Natural-language to SQL success, refusals by reason, OpenAI latency and token cost, Athena bytes and cost per query, failures, email sent and email failed | Success below 80 percent over 1 hour. Any email failure. Athena spend above `$X` per day. OpenAI errors above 5 percent | Tempo spans and `backend/telemetry/dashboards/agentic_search.json` already split `results`, `invalid`, `mail_failed`, `rejected`, and `failed`. [Issue #189](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/189) is still open. Refusal reasons, OpenAI token cost, and Athena bytes are not metrics. Athena bytes for the OLAP workgroup also need CloudWatch metrics enabled on `lab-data-integrations-interface-olap`. |
| Cost | AWS Budgets, Cloudflare billing notifications, OpenAI usage | Alert at 80 percent of each budget | No budget resources in Terraform. The maintenance Athena workgroup publishes CloudWatch metrics. The data platform workgroups do not. |
| Config drift | A nightly job that compares required secret and binding names, and compares hashes of the values | The job fails when a required name is missing or a hash differs from the recorded hash | Not in the repo. The compare must log names and hashes, never values. |

## Routing

Send Grafana contact points to Mark's email and to Slack. Also send a webhook to a Cursor automation for the alerts that have a playbook in [SRE agents](sre_agents.md). PagerDuty is not part of this plan.

The contact point that calls Cursor must send the bearer key, and the stored URL must not have a trailing newline. A trailing newline is a known cause of HTTP 400 on the automation webhook while a scheduled run of the same automation succeeds ([forum thread](https://forum.cursor.com/t/automation-webhook-returns-http-400-while-scheduled-trigger-works/171792)).

## Code and Terraform to add later

The items below are later instrumentation work. They are the gaps behind the table, and they are outside this documentation change.

- Jetstream RSS, if you want it from the process as well as from Cloudflare container metrics. Cursor age can be a Grafana query on `bluesky_jetstream.cursor.timestamp`. A separate age series is optional.
- Flush duration. The per-flush JSON log has rows, megabytes, and the flush reason, and it has no duration field. Add one if you want to graph how long a flush took.
- A counter for Supabase auth failures by reason, next to the existing log line in `backend/auth.py`.
- Refusal reason, Athena bytes scanned, and email result as attributes or counters on the search span. Email failure is already an `outcome` of `mail_failed`. Token cost is not.
- `bytes_scanned_cutoff_per_query` on the OLAP workgroup, and `publish_cloudwatch_metrics_enabled` on both data platform workgroups. The maintenance workgroup already publishes metrics. The cutoff field is the Athena limit documented in the DevOps page.
