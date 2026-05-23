# Demo App Setup

## Overview

This runbook covers how to set up and containerize the demo FastAPI app with OpenTelemetry instrumentation.

## Dependencies

The app requires the following dependencies. Reference `telemetry/app/pyproject.toml` for the full list.

Key OpenTelemetry packages:
- `opentelemetry-distro` — core OTel SDK and auto-instrumentation bootstrap
- `opentelemetry-exporter-otlp` — exports telemetry data to the OTel Collector
- `opentelemetry-instrumentation-fastapi` — auto-instruments FastAPI routes
- `opentelemetry-instrumentation-logging` — forwards Python logs to OTel
- `uvicorn` — ASGI server to run the FastAPI app

To install:
Write/copy the pyproject.toml and run `uv sync`

## Dockerfile

Reference `telemetry/app/Dockerfile` for an example. Key points:

- Uses `python:3.12-slim` as the base image
- Copies the `uv` binary from `ghcr.io/astral-sh/uv:latest` for fast dependency installation
- Installs dependencies via `uv sync --frozen` using the lockfile
- Starts the app with `uv run opentelemetry-instrument uvicorn` so the OTel SDK wraps the app on startup

## Running with Docker Compose

Reference `telemetry/app/docker-compose.yml` for an example. The compose file defines two services:

- `app` — your FastAPI app, built from the Dockerfile
- `otel-lgtm` — the Grafana LGTM stack that receives and stores telemetry

Key environment variables set on the app service:

- `OTEL_EXPORTER_OTLP_ENDPOINT` — points the OTel SDK to the collector (`http://otel-lgtm:4318`)
- `OTEL_LOGS_EXPORTER` — enables log forwarding to OTel (`otlp`)
- `OTEL_SERVICE_NAME` — the name that appears in Grafana for this service
- `OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED` — enables automatic Python log instrumentation

To run:
```bash
cd telemetry/app
docker compose up
```

To rebuild after code or dependency changes:
```bash
docker compose up --build
```
