# Running the Backend App

## Overview

This runbook covers starting `backend/` locally and how its telemetry is
wired. See [HOW_TO_ADD_OBSERVABILITY_GRAFANA.md](HOW_TO_ADD_OBSERVABILITY_GRAFANA.md)
for the Grafana Cloud stack this exports to.

## Run

```bash
uv run uvicorn backend.main:app --reload --port 8000
```

That is the whole command — no `opentelemetry-instrument` wrapper and no
`--env-file`. `backend/main.py` calls `load_dotenv()` at import, so the root
`.env` is read before `setup_telemetry()` runs.

## How telemetry is wired

`backend/telemetry/setup.py` builds the `TracerProvider` and `LoggerProvider`
in code and instruments the FastAPI app itself, mirroring
`bluesky_ingestion_jetstream/telemetry/`. Service name and OTLP endpoints are
constants in `backend/telemetry/constants.py`, not environment variables.

One env var is left:

| Variable | Value |
|---|---|
| `OTEL_EXPORTER_OTLP_HEADERS` | `Authorization=Basic%20<base64(instanceID:token)>` |

The `%20` matters — the Python OTLP exporter needs the header value
URL-encoded, and a literal space breaks it. Grafana Cloud shows a ready-made
value on the stack's **OpenTelemetry** page.

## Run without telemetry

Unset `OTEL_EXPORTER_OTLP_HEADERS`. `setup_telemetry()` checks for the token
and returns early when it is absent, so nothing is exported and nothing
crashes. The app is otherwise unaffected.

This replaces the old switch, which was whether the process started through
the `opentelemetry-instrument` wrapper. That wrapper is no longer used.

## Verifying it worked

1. Hit an endpoint a few times to generate data:
   ```bash
   curl http://localhost:8000/health
   ```
2. Check Grafana Cloud (Application Observability or Explore) for a `backend`
   service with matching traces and logs.
3. If nothing shows up, confirm `OTEL_EXPORTER_OTLP_HEADERS` was actually
   present in the environment the process saw — the startup log line says
   which path it took (`telemetry enabled as backend`, or
   `OTEL_EXPORTER_OTLP_HEADERS unset; running without telemetry`).

## Deploying

See [HOW_TO_DEPLOY_BACKEND_TO_RAILWAY.md](HOW_TO_DEPLOY_BACKEND_TO_RAILWAY.md).
`railway/backend.json` runs the same uvicorn command, and Railway injects the
**Variables** tab contents directly into the container's environment, so the
token arrives the same way `.env` supplies it locally.
