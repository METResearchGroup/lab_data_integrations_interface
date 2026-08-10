# How to Deploy the Backend to Railway

## Overview

This runbook covers deploying `backend/` (the FastAPI app) to Railway as its
own project. The ingester deploys separately — see
[HOW_TO_DEPLOY_JETSTREAM_TO_RAILWAY.md](HOW_TO_DEPLOY_JETSTREAM_TO_RAILWAY.md).

| | |
|---|---|
| Config file | `railway/backend.json` |
| Start command | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
| Type | HTTP service, gets a Railway domain |

## Build context

Imports are absolute and rooted at the repo root (`from backend.main...`), and
there is one `pyproject.toml` / `uv.lock` for the whole repo. Scoping **Root
Directory** to `backend/` removes the lockfile from the build context.

So **leave Root Directory unset (`/`)**. What separates this service from the
ingester is the config file it reads, not the build context.

## Pointing the service at its config

Railway auto-detects a `railway.json` at the root of the build context. One
build context cannot describe two services, so this one points at its config
explicitly:

**Service Settings → Config-as-code → Railway Config File** → `railway/backend.json`

Nothing about the filename links it to this service automatically — that field
is the only connection. Skip it and the service falls back to auto-detection
and will not pick up the right start command.

`railway/backend.json` also sets `watchPatterns` scoped to `backend/**` plus
the lockfiles, so pushes that only touch the ingester do not redeploy this
service. The list includes `railway/backend.json` itself, so editing the start
command still triggers a deploy.

## Environment variables

Set these under the service's **Variables** tab. Nothing is shared with the
ingester's project — a variable set there is invisible here.

| Variable | Required | Notes |
|---|---|---|
| `CORS_ORIGINS` | Recommended | Comma-separated allowed origins (`backend/main.py`). Set to the deployed frontend's URL. Defaults to `http://localhost:3000`. |
| `OTEL_EXPORTER_OTLP_HEADERS` | Recommended | Grafana Cloud token, `Authorization=Basic%20<base64(instanceID:token)>`. Unset it to run without telemetry — `setup_telemetry()` returns early rather than crashing. |

The backend serves only `/health` and needs no AWS credentials. Its service
name and OTLP endpoints are constants in `backend/telemetry/constants.py`, so
the token is the only telemetry variable. See
[HOW_TO_RUN_BACKEND_APP.md](HOW_TO_RUN_BACKEND_APP.md) for how that wiring
works locally.

## Deploy steps

1. In Railway, create a project from this GitHub repo.
2. Leave **Root Directory** unset (`/`).
3. Set **Config-as-code → Railway Config File** to `railway/backend.json`.
4. Add the env vars above under **Variables**.
5. Deploy.
6. Set `CORS_ORIGINS` to the deployed frontend's URL so it can call this
   service.

## Verifying

`GET /health` returns `{"status": "ok"}` on the generated Railway domain.

`healthcheckPath` is set to `/health` in the config, so a deploy that fails to
come up will not replace a healthy one.
