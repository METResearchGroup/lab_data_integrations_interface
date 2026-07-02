# Backend Railway Deploy

## Overview

This runbook covers deploying `backend/` (the FastAPI app) to Railway. The
app imports via absolute paths rooted at the repo root (`from backend.routes...`,
`from data_platform.aws...`), so Railway must build/run from the repo root,
not from `backend/` as a scoped root directory.

## Repo setup

- `railway.json` at the repo root configures the build/start command — no
  manual dashboard config needed for that part. Reference it for the exact
  build/start commands.

## Environment variables

The backend only needs a small subset of the repo's env vars — most of the
keys in the root `.env` (`BLUESKY_*`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`GOOGLE_API_KEY`, `OPENROUTER_API_KEY`) belong to `data_platform` collectors
and LLM feature generation, not the backend. Do not copy the whole `.env`
into the Railway service.

Set these in the Railway service's **Variables** tab:

| Variable | Required | Notes |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | Yes | boto3 default credential chain — used by `Athena`/`S3` in `data_platform/aws/*` (`backend/routes/posts.py`). Locally this comes from `~/.aws`, which won't exist on Railway. |
| `AWS_SECRET_ACCESS_KEY` | Yes | Paired with the above. |
| `AWS_SESSION_TOKEN` | Only if using temporary/STS credentials | Omit for a long-lived IAM user's static keys. |
| `CORS_ORIGINS` | Recommended | Comma-separated list of allowed origins (`backend/main.py`). Set to the deployed frontend's URL. Defaults to `http://localhost:3000` if unset. |

The IAM credentials need permission for: `athena:StartQueryExecution`,
`athena:GetQueryExecution`, `athena:GetQueryResults` on workgroup
`lab-data-integrations-interface-olap`, Glue read access to the
`lab_data_integrations_interface` database, and `s3:GetObject`/`s3:PutObject`
on the `lab-data-integrations-interface` bucket (query results + presigned
download URLs).

`AWS_DEFAULT_REGION` is **not** required — `data_platform/aws/constants.py`
hardcodes `us-east-2` as the default passed explicitly to each boto3 client.

## Deploy steps

1. In Railway, create a new service from the GitHub repo (the whole
   monorepo — Railway needs repo-root context for imports to resolve).
2. Leave **Root Directory** unset (defaults to `/`). Do **not** scope it to
   `backend/` — `data_platform` wouldn't be present in that build context.
3. Railway auto-detects `railway.json` for the build/start command.
4. Add the env vars from the table above under **Variables**.
5. Deploy, then verify `GET /health` returns `{"status": "ok"}` on the
   generated Railway domain.
6. Add `CORS_ORIGINS` set to the deployed frontend's URL so it can call the
   backend.
