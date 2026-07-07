# Running the Backend With and Without Observability

## Overview

This runbook covers how to start `backend/` with telemetry exporting to
Grafana Cloud, and how to run it without — no code branching or feature flag
involved. See [HOW_TO_ADD_OBSERVABILITY_GRAFANA.md](HOW_TO_ADD_OBSERVABILITY_GRAFANA.md)
for the dependencies/env vars this assumes are already in place.

## How the on/off switch works

The OpenTelemetry SDK is only configured when the process is started through
the `opentelemetry-instrument` wrapper (installed via `opentelemetry-distro`).
That wrapper reads the `OTEL_*` env vars at startup and builds the
`TracerProvider` + OTLP exporter before your app code runs.

If you start the app **without** that wrapper, `trace.get_tracer(__name__)`
in `backend/main.py` returns a no-op tracer — any manual
`with tracer.start_as_current_span(...)` blocks silently do nothing. No
crash, nothing exported, no auto-instrumentation of FastAPI or botocore
either.

So the switch is just: prefix the start command with `opentelemetry-instrument`,
or don't.

## Run without telemetry

```bash
uv run uvicorn backend.main:app --reload --port 8000
```

Use this for normal local development when you don't need to look at traces.

## Run with telemetry

```bash
uv run --env-file .env opentelemetry-instrument uvicorn backend.main:app --reload --port 8000
```

`--env-file .env` matters here: `opentelemetry-instrument` reads the
`OTEL_*` vars from the process environment *before* `backend/main.py` is
imported, so relying on `python-dotenv` loading `.env` from inside the app
would be too late — the SDK would already be configured (or not) by then.

## Verifying it worked

1. Hit an endpoint a few times to generate data:
   ```bash
   curl http://localhost:8000/health
   curl "http://localhost:8000/posts/recent?dataset_id=<id>"
   ```
2. Check Grafana Cloud (Application Observability or Explore, per
   [HOW_TO_ADD_OBSERVABILITY_GRAFANA.md](HOW_TO_ADD_OBSERVABILITY_GRAFANA.md))
   for a `backend` service with matching traces/logs.
3. If nothing shows up, confirm `OTEL_EXPORTER_OTLP_ENDPOINT` /
   `OTEL_EXPORTER_OTLP_HEADERS` are actually present in the environment the
   process saw (`opentelemetry-instrument` fails silently/exports nowhere on
   auth or endpoint misconfiguration — it does not crash the app).

## Deploying

`railway.json`'s `startCommand` runs the `opentelemetry-instrument`-wrapped
form above, so telemetry is on by default in the deployed backend — no
`--env-file` needed there, since Railway injects the **Variables** tab
contents directly into the container's environment.

The one remaining step: the env vars from
[HOW_TO_ADD_OBSERVABILITY_GRAFANA.md](HOW_TO_ADD_OBSERVABILITY_GRAFANA.md)
(`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`,
`OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_SERVICE_NAME`, `OTEL_LOGS_EXPORTER`,
`OTEL_METRICS_EXPORTER`) still need to be added to Railway's **Variables**
tab (see [backend-railway-deploy.md](backend-railway-deploy.md)) — without
them, the wrapper runs but exports nowhere.
