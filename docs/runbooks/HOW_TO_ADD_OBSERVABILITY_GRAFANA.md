# Grafana Cloud Observability Setup

## Overview

This runbook covers wiring `backend/` up to **Grafana Cloud** for traces,
logs, and metrics — as opposed to the self-hosted `otel-lgtm` stack used by
the `telemetry/app` demo (see [lgtm-stack-setup.md](lgtm-stack-setup.md)).

Grafana Cloud's OTLP Gateway is a single managed ingest endpoint that sits in
front of your stack's hosted Tempo (traces), Loki (logs), and Mimir
(Prometheus-compatible metrics). It routes incoming data to the right backend
automatically based on signal type — there is no separate OTel Collector to
run or configure yourself, unlike the `otel-lgtm` container.

## Prerequisites

- A Grafana Cloud account with a stack provisioned.
- An **Access Policy token** (or the classic API key) scoped for
  `metrics:write`, `logs:write`, and `traces:write` — generated from
  Grafana Cloud → your stack → **OpenTelemetry** (or **Connections → Add new
  connection → OpenTelemetry**) page. That page also shows your stack's OTLP
  Gateway URL and a ready-made `Authorization` header value.

## Dependencies

Already added to the root `pyproject.toml` as hard dependencies (not
optional — `backend/` may add manual spans, which means a hard
`from opentelemetry import trace` import, so the packages must always be
present):

```bash
uv add opentelemetry-distro opentelemetry-exporter-otlp opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-logging opentelemetry-instrumentation-botocore
```

- `opentelemetry-distro` — core SDK.
- `opentelemetry-exporter-otlp` — ships spans/logs/metrics to Grafana Cloud's
  OTLP Gateway.
- `opentelemetry-instrumentation-fastapi` — instruments `backend/main.py`'s
  routes, applied in code by `backend/telemetry/setup.py`.
- `opentelemetry-instrumentation-logging` — forwards Python `logging` calls.
- `opentelemetry-instrumentation-botocore` — auto-instruments boto3 calls in
  `data_platform/aws/*`.

## Environment variables

Both services build their providers in code rather than through the
`opentelemetry-instrument` CLI, so service names and OTLP endpoints are
constants (`backend/telemetry/constants.py`,
`bluesky_ingestion_jetstream/telemetry/constants.py`), not env vars. Only the
credential is environmental:

| Variable | Value | Notes |
|---|---|---|
| `OTEL_EXPORTER_OTLP_HEADERS` | `Authorization=Basic%20<base64(instanceID:token)>` | Note the `%20` — the Python OTLP exporter needs the header value URL-encoded, a literal space breaks it. |

It lives in the root `.env` for local dev; mirror it into Railway's
**Variables** tab per service — each is its own project with its own
variables, so it must be set twice. See
[HOW_TO_DEPLOY_BACKEND_TO_RAILWAY.md](HOW_TO_DEPLOY_BACKEND_TO_RAILWAY.md) and
[HOW_TO_DEPLOY_JETSTREAM_TO_RAILWAY.md](HOW_TO_DEPLOY_JETSTREAM_TO_RAILWAY.md).

Setting it is also the on/off switch: `setup_telemetry()` returns early when
the token is absent, so an unconfigured process exports nothing rather than
defaulting to localhost.

Importing the HTTP exporter pins the protocol, which is why
`OTEL_EXPORTER_OTLP_PROTOCOL` is no longer needed — Grafana Cloud's gateway
requires `http/protobuf`, and the choice is now made by the import rather than
by an env var the deployment could forget.

## Viewing data in Grafana Cloud

1. **Application Observability** (guided, recommended first stop): in your
   Grafana Cloud stack, go to **Observability → Application**. Once the app
   has sent data (see
   [HOW_TO_RUN_BACKEND_APP.md](HOW_TO_RUN_BACKEND_APP.md)), a
   service card appears named after the `SERVICE_NAME` constant, with RED metrics,
   trace search, and correlated logs pre-wired.
2. **Explore** (raw queries): pick the Tempo/Loki/Mimir datasource from the
   dropdown — they're already provisioned as part of the stack, no manual
   data source setup needed.
   - Tempo (TraceQL): `{ resource.service.name = "backend" }`
   - Loki (LogQL): `{ service_name = "backend" }`
   - Mimir (PromQL): `http_server_duration_milliseconds_bucket{service_name="backend"}`
