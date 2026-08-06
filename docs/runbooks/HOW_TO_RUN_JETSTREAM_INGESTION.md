# How to Run Jetstream Ingestion

## Overview

`bluesky_ingestion_jetstream/` streams Bluesky events, buffers them by record
type, and commits batches to the Iceberg tables in the `bluesky_raw` Glue
catalog. This runbook covers running it locally.

## Prerequisites

- Dependencies installed: `uv sync`.
- AWS credentials on the default boto3 chain (`AWS_PROFILE`, env keys, or SSO)
  with access to Glue, S3, and DynamoDB in `us-east-2`.
- The four Iceberg tables already created — see
  [HOW_TO_SETUP_ICEBERG_TABLES.md](HOW_TO_SETUP_ICEBERG_TABLES.md). The ingester
  never issues DDL; missing tables raise on startup.

Everything else is a constant in `bluesky_ingestion_jetstream/aws/constants.py`
(region, bucket, Glue database, cursor table), not configuration.

## Environment variable

One variable, read from the root `.env` via `load_dotenv()`:

| Variable | Value |
|---|---|
| `OTEL_EXPORTER_OTLP_HEADERS` | `Authorization=Basic%20<base64(instanceID:token)>` |

This is the Grafana Cloud token that telemetry exports with. The `%20` matters —
the Python OTLP exporter needs the header value URL-encoded, and a literal space
breaks it. Grafana Cloud shows a ready-made value on the stack's
**OpenTelemetry** page.

The service name and OTLP endpoints are set in
`bluesky_ingestion_jetstream/telemetry/constants.py`, not by env var, so the
shared `OTEL_SERVICE_NAME` in `.env` (which names the backend) does not apply.

## Run

```bash
PYTHONPATH=. uv run python bluesky_ingestion_jetstream.main
```

The process runs until stopped. `Ctrl-C` or `SIGTERM` shuts it down cleanly,
flushing telemetry on the way out.

On start it logs the cursor it is resuming from, then a JSON line per flush:

```json
{"event": "flush", "reason": "age", "posts_rows": 4490, "posts_mb": 2.81, ...}
```

`reason` is `size` when the buffers hit their byte threshold and `age` when the
oldest rows have waited long enough.

## Run without telemetry

Unset `OTEL_EXPORTER_OTLP_HEADERS`. `setup_telemetry()` checks for the token and
skips wiring up the providers when it is absent, so instrument calls become
no-ops. Ingestion is unaffected — nothing is exported, and nothing crashes.

## Viewing the data

See [HOW_TO_SETUP_JETSTREAM_DASHBOARD.md](HOW_TO_SETUP_JETSTREAM_DASHBOARD.md)
for the Grafana dashboard over these metrics and logs.
