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

- `opentelemetry-distro` — core SDK + the `opentelemetry-instrument` CLI that
  bootstraps everything below from env vars.
- `opentelemetry-exporter-otlp` — ships spans/logs/metrics to Grafana Cloud's
  OTLP Gateway.
- `opentelemetry-instrumentation-fastapi` — auto-instruments `backend/main.py`'s
  routes.
- `opentelemetry-instrumentation-logging` — forwards Python `logging` calls.
- `opentelemetry-instrumentation-botocore` — auto-instruments the boto3/Athena/S3
  calls in `backend/routes/posts.py` (`data_platform/aws/*`), since that's the
  app's only outbound I/O.

## Environment variables

Set these (already present in the root `.env` for local dev — mirror them in
Railway's **Variables** tab for the deployed backend, see
[backend-railway-deploy.md](backend-railway-deploy.md)):

| Variable | Value | Notes |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `https://otlp-gateway-<region>.grafana.net/otlp` | Base gateway URL — the SDK appends `/v1/traces`, `/v1/logs`, `/v1/metrics` per signal automatically. Don't point this at a signal-specific path. |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | Required. `opentelemetry-distro` defaults this to `grpc` if unset (see `opentelemetry/distro/__init__.py`'s `os.environ.setdefault(...)` calls) — Grafana Cloud's gateway needs `http/protobuf`, so this is the one var that must be set explicitly. |
| `OTEL_EXPORTER_OTLP_HEADERS` | `Authorization=Basic%20<base64(instanceID:token)>` | Note the `%20` — the Python OTLP exporter needs the header value URL-encoded, a literal space breaks it. |
| `OTEL_SERVICE_NAME` | `backend` | add this so the service shows up with a clear name in Grafana instead of a default. |

`OTEL_TRACES_EXPORTER`, `OTEL_METRICS_EXPORTER`, and `OTEL_LOGS_EXPORTER` do
**not** need to be set — `opentelemetry-distro` defaults all three to `otlp`
via `os.environ.setdefault(...)` before the SDK reads them (verified in the
installed package source and empirically by inspecting the configured
providers under `opentelemetry-instrument`). All three signals export by
default; only the protocol needs overriding.

## Viewing data in Grafana Cloud

1. **Application Observability** (guided, recommended first stop): in your
   Grafana Cloud stack, go to **Observability → Application**. Once the app
   has sent data (see
   [HOW_TO_RUN_BACKEND_APP.md](HOW_TO_RUN_BACKEND_APP.md)), a
   service card appears named after `OTEL_SERVICE_NAME`, with RED metrics,
   trace search, and correlated logs pre-wired.
2. **Explore** (raw queries): pick the Tempo/Loki/Mimir datasource from the
   dropdown — they're already provisioned as part of the stack, no manual
   data source setup needed.
   - Tempo (TraceQL): `{ resource.service.name = "backend" }`
   - Loki (LogQL): `{ service_name = "backend" }`
   - Mimir (PromQL): `http_server_duration_milliseconds_bucket{service_name="backend"}`
