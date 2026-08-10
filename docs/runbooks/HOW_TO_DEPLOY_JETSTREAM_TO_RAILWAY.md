# How to Deploy Jetstream Ingestion to Railway

## Overview

This runbook covers deploying `bluesky_ingestion_jetstream/` to Railway as its
own project. The backend deploys separately — see
[HOW_TO_DEPLOY_BACKEND_TO_RAILWAY.md](HOW_TO_DEPLOY_BACKEND_TO_RAILWAY.md).

| | |
|---|---|
| Config file | `railway/bluesky_ingestion_jetstream.json` |
| Start command | `python -m bluesky_ingestion_jetstream.main` |
| Type | Long-running worker, no HTTP listener and no domain |

## Prerequisites

The four Iceberg tables and the DynamoDB cursor table must already exist —
see [HOW_TO_SETUP_ICEBERG_TABLES.md](HOW_TO_SETUP_ICEBERG_TABLES.md). The
ingester never issues DDL; missing tables raise on startup.

## Build context

Imports are absolute and rooted at the repo root (`from
bluesky_ingestion_jetstream.aws...`), and there is one `pyproject.toml` /
`uv.lock` for the whole repo. Scoping **Root Directory** to
`bluesky_ingestion_jetstream/` removes the lockfile from the build context.

So **leave Root Directory unset (`/`)**. What separates this service from the
backend is the config file it reads, not the build context.

## Pointing the service at its config

Railway auto-detects a `railway.json` at the root of the build context. One
build context cannot describe two services, so this one points at its config
explicitly:

**Service Settings → Config-as-code → Railway Config File** →
`railway/bluesky_ingestion_jetstream.json`

Nothing about the filename links it to this service automatically — that field
is the only connection. Skip it and the service falls back to auto-detection
and will not pick up the right start command.

The config also sets:

- `watchPatterns`, scoped to `bluesky_ingestion_jetstream/**` plus the
  lockfiles. Without them every push to `main` redeploys the ingester, which
  drops the stream and replays from the stored cursor for no reason. The list
  includes the config file itself, so start-command edits still deploy.
- `restartPolicyType: ALWAYS`, so a stream that dies comes back up.
- `numReplicas: 1`. Keep it there — replicas share one DynamoDB cursor item
  and would double-write.

## Environment variables

Set these under the service's **Variables** tab. Nothing is shared with the
backend's project — a variable set there is invisible here.

| Variable | Required | Notes |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | Yes | boto3 default chain — Glue, S3, and DynamoDB in `us-east-2`. Locally this comes from `~/.aws`, which does not exist on Railway. |
| `AWS_SECRET_ACCESS_KEY` | Yes | Paired with the above. |
| `AWS_SESSION_TOKEN` | Only for temporary/STS credentials | Omit for a long-lived IAM user's static keys. |
| `OTEL_EXPORTER_OTLP_HEADERS` | Recommended | Grafana Cloud token, `Authorization=Basic%20<base64(instanceID:token)>`. Unset it to run without telemetry — `setup_telemetry()` returns early rather than crashing. |

Region, bucket, Glue database, cursor table, service name, and OTLP endpoints
are constants in `bluesky_ingestion_jetstream/`, not env vars.

`AWS_DEFAULT_REGION` is not required — `us-east-2` is passed explicitly to
each boto3 client.

## Deploy steps

1. In Railway, create a project from this GitHub repo.
2. Leave **Root Directory** unset (`/`).
3. Set **Config-as-code → Railway Config File** to
   `railway/bluesky_ingestion_jetstream.json`.
4. Add the env vars above under **Variables**.
5. Deploy.

## Verifying

The deploy logs show the cursor it resumed from, then a JSON line per flush:

```json
{"event": "flush", "reason": "age", "posts_rows": 4490, "posts_mb": 2.81, ...}
```

Railway generates no domain for this service — it has no HTTP listener. That
is expected, not a broken deploy.

Railway sends `SIGTERM` on redeploy, which `main.py` converts into a clean
shutdown and a final telemetry flush, so a redeploy costs at most a short
replay from the stored cursor.

See [HOW_TO_SETUP_JETSTREAM_DASHBOARD.md](HOW_TO_SETUP_JETSTREAM_DASHBOARD.md)
for the Grafana dashboard over these metrics and logs.
