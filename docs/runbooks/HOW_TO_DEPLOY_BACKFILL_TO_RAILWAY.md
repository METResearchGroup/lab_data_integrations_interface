# How to Deploy Backfill Workers to Railway

## Overview

Deploys `bluesky_backfill_app/fetch_repos/` as Railway project
`bluesky-backfill`, service `fetch-repos`: 4 replicas pulling DIDs off the
`bluesky-backfill-dids` queue. Queue users first, see
[HOW_TO_QUEUE_BACKFILL_USERS.md](HOW_TO_QUEUE_BACKFILL_USERS.md).

| | |
|---|---|
| Config | `railway/bluesky_backfill_app/.railway/railway.ts` (Railway Infrastructure as Code) |
| Start command | `python -m bluesky_backfill_app.fetch_repos.main` |
| Type | Long-running worker, no HTTP listener and no domain |

Unlike the backend and Jetstream (`railway/*.json`, Config as Code), this file is
not read on deploy. Changes reach Railway only through `railway config apply`.

## Prerequisites

- Railway CLI 5.42.1 or newer (`npm i -g @railway/cli`), then `railway login`.
- Node, to install the IaC SDK.

## Steps

From `railway/bluesky_backfill_app/.railway/`:

```bash
npm ci

# First time only: create the project and link this directory to it.
railway init --name bluesky-backfill

railway config plan
railway config apply
```

Then set the variables below on the `fetch-repos` service, in the dashboard
(**Variables** tab) or with `railway variables --service fetch-repos --set KEY=value`.
The IaC file only declares them, with `preserve()`, so their values never go in git.

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | Yes | DynamoDB, SQS, and S3 in `us-east-2`. |
| `AWS_SECRET_ACCESS_KEY` | Yes | Paired with the above. |
| `OTEL_EXPORTER_OTLP_HEADERS` | Recommended | Grafana Cloud token, same value as Jetstream. Unset runs without telemetry. |

Copy these from the Jetstream project's service variables. The IAM user also
needs SQS and the backfill DynamoDB tables, which Jetstream does not use.

## Verifying

Deploy logs show `starting fetch run <run_id>` per replica, then
`flushed N dids (...) to M files` as buffers fill or age out (30 min).
