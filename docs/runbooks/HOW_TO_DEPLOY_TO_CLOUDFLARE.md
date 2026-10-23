# How to Deploy to Cloudflare

## Overview

The FastAPI backend runs as a Cloudflare Container. The Next.js UI in `ui/`
runs as a Cloudflare Worker, built with vinext. Object storage stays on AWS
S3. This deploy does not use Cloudflare R2.

Railway config stays in the repo. See [What can be removed later](#what-can-be-removed-later).

| | |
|---|---|
| API config | `cloudflare/backend/wrangler.jsonc` |
| API image | `cloudflare/backend/Dockerfile` (build context is the repo root) |
| API start | `uvicorn backend.main:app --host 0.0.0.0 --port 8000` |
| API Worker name | `ldi-api-preview` |
| UI config | `ui/cloudflare.config.ts` |
| UI deploy | `npm run deploy:vinext` from `ui/` |
| UI Worker name | `ldi-ui-preview` |
| Account | `CLOUDFLARE_ACCOUNT_ID` from Secrets Manager. Do not commit it. |
| Subdomain | `mind-technology-lab.workers.dev` |

Preview URLs, once deployed:

- API: `https://ldi-api-preview.mind-technology-lab.workers.dev`
- UI: `https://ldi-ui-preview.mind-technology-lab.workers.dev`

These names are preview Workers on the lab account. They are not a production
cutover. `workers.dev` URLs are public unless Access is put in front of them.

The pattern follows
[mind_technology_lab_experiments#39](https://github.com/METResearchGroup/mind_technology_lab_experiments/pull/39)
for the UI (vinext, `workers.dev`, observability, secrets kept out of git).
That demo ran FastAPI as a Python Worker. This API does not. See the next
section.

## Containers vs Workers

The backend is a Container. A plain Worker is the wrong runtime for it.

A Worker has no process that stays up between requests. This API is a CPython
process: uvicorn, FastAPI, PyIceberg, PyArrow, and the LangGraph query path.
`/query` returns 202 and finishes the Athena query, the model call, and the
email in a background task inside that process (`backend/routes/query.py`).
The rate limiter in `backend/rate_limit.py` is in-memory. None of that fits a
request-scoped isolate, and the native wheels do not run on Pyodide.

The UI does fit a Worker. vinext checked this app at 100% compatibility,
including `src/proxy.ts`, and deploys it with `@vinext/cloudflare`. OpenNext
was not needed.

### Cold starts

A sleeping or newly provisioned container has to pull the image and import
the API before `/health` answers. Expect several seconds after a normal
sleep, and longer the first time the account provisions the instance (the
dashboard can show "provisioning" for a few minutes). On the first preview
provision the image pull took about 3 minutes and the VM start took about 6
seconds. The next start, after a rollout, answered `/health` in about 6
seconds. The Worker waits up to 180 seconds for port 8000
(`cloudflare/backend/src/index.ts`). The helper's default wait is 20 seconds,
which is too short for this image.

### Instance lifetime and sleep

One Durable Object name, `api`, plus `max_instances: 1`, keeps a single
container. `sleepAfter` is `30m`. The timer resets when a request is proxied
through the Worker. It does not reset while `/query`'s background task is
still running after the 202. A query that runs longer than 30 minutes with no
further HTTP traffic is stopped.

There is no always-on switch. Billing stops when the instance sleeps. Disk is
ephemeral and is wiped on sleep, which is fine: tables live in S3 and Glue,
and the rate-limiter state is allowed to reset.

To keep an instance warm, add a cron on the Worker that fetches `/health`
more often than `sleepAfter`. Five minutes is enough for the 30 minute
window:

```jsonc
"triggers": { "crons": ["*/5 * * * *"] }
```

```ts
async scheduled(_controller, env, ctx) {
  const container = env.API_CONTAINER.getByName("api");
  ctx.waitUntil(container.fetch("https://ldi-api-preview.internal/health"));
}
```

That cron is not enabled. It turns the preview into an always-on bill.

Overriding `onActivityExpired` and not stopping the container also prevents
sleep. That is the shape to use for a process that must not stop. It bills
for every second the instance stays up.

Cloudflare can still restart the host. The container gets SIGTERM, then about
15 minutes before SIGKILL. The Jetstream and backfill processes already
handle SIGTERM.

### Instance size

`standard-1`: 1/2 vCPU, 4 GiB memory, 8 GB disk. `lite` (256 MiB) and `basic`
(1 GiB) are too small for this import set. The image has to fit on the disk.
The largest preset is `standard-4` (4 vCPU, 12 GiB, 20 GB). If the process is
killed during import, move `instance_type` to `standard-2` (1 vCPU, 6 GiB,
12 GB) and redeploy.

### Cost

Containers require the Workers Paid plan ($5 per month per account, if the
account is not already paying it). Included each month: 25 GiB-hours of
memory, 375 vCPU-minutes, 200 GB-hours of disk. Past that, memory is
$0.0000025 per GiB-second, CPU is $0.000020 per active vCPU-second, and disk
is $0.00000007 per GB-second. Egress in North America and Europe is $0.025
per GB after 1 TB. Figures are from the Containers pricing page as of
2026-10-05 and the limits page as of 2026-10-21.

`standard-1` left running all month is about 4 GiB × 730 hours. Memory
overage is about $26. Disk overage on the 8 GB volume is about $1.40. CPU is
billed on active use, not on the 1/2 vCPU reservation. An idle process is a
few dollars; a pegged 1/2 vCPU adds about $25. A single always-on API is
roughly $35 to $60 per month on top of the plan, before logs and egress.

Scale to zero is the preview default. One 30-minute wake per day for a month
is about 60 GiB-hours, near $0.30 of memory past the included 25, plus the
plan. The UI Worker for this lab's traffic fits in the paid request allotment.

### Ingestion and backfill

Jetstream and the backfill fetch worker belong on Containers if they are
turned back on. They are infinite loops (a WebSocket firehose, an SQS long
poll). A Worker cannot host either. Each needs its own Container, `max_instances: 1`
(the Jetstream cursor in DynamoDB is single-writer), and sleep disabled, by
the cron above or by not stopping on `onActivityExpired`.

Do not put them on the API container. A sleep after 30 idle minutes would
drop the firehose, and a second copy would double-write.

They are not deployed here. Railway is already shut down, and starting either
process writes to the production bucket and DynamoDB tables. Turning them on
is a separate decision. An always-on `standard-1` for each is another $35 to
$60 per month, so both plus the API is on the order of $100 to $180 if all
three stay up.

`telemetry/app` was not a Railway service. It is not part of this deploy.

## What was ported

| Service | Railway / other | This change |
|---|---|---|
| FastAPI backend | `railway/backend.json`, HTTP | Ported to Container `ldi-api-preview` |
| Next.js UI | Vercel, not Railway | Ported to Worker `ldi-ui-preview` |
| Jetstream ingester | `railway/bluesky_ingestion_jetstream.json`, no HTTP | Not ported. Needs an always-on Container. Would write production data. |
| Backfill fetch workers | `railway/bluesky_backfill_app/.railway/railway.ts` | Not ported. Same reason. SIGTERM drain already fits the 15 minute container grace. |
| `gather_users` | CLI, not Railway | Not ported |
| `telemetry/app` | Sample app, not Railway | Not ported |

## Backend

### Build context

Imports are absolute from the repo root (`from backend.main`, `from lib.aws`,
`from bluesky_ingestion_jetstream...`). One `pyproject.toml` / `uv.lock`
covers the repo. The image is built with the repo root as context
(`image_build_context` in the Wrangler config). `.dockerignore` keeps `.venv`,
git, and experiment data out of the context.

The image runs `uv sync --frozen --no-dev --no-install-project` and leaves the
packages on `PYTHONPATH`. That matches `uvicorn backend.main:app` on Railway.
Env vars arrive as process environment. `backend/main.py` calls `load_dotenv()`,
which does not override variables that are already set. `EnvVarsContainer` in
`lib/load_env_vars.py` reads `OPENAI_API_KEY` from the environment after
loading the root `.env`, which is absent in the image. No second loader was
added.

### Pointing traffic at the container

`ldi-api-preview` is a Worker whose only job is to route every request to one
container. The container listens on port 8000. Internet egress is on, because
the API calls AWS, Supabase, OpenAI, and Gmail.

`CORS_ORIGINS` is a Wrangler var, not a secret. `backend/main.py` splits on
commas and does not trim, so the value must not contain spaces.

### Secrets

From `cloudflare/backend/`, with `CLOUDFLARE_API_TOKEN` and
`CLOUDFLARE_ACCOUNT_ID` exported:

```bash
# stdin, so the value is not a shell argument and does not land in the command line
printf '%s' "$AWS_ACCESS_KEY_ID" | npx wrangler secret put AWS_ACCESS_KEY_ID
```

Repeat for each secret in the table below. `wrangler secret put` deploys a
new Worker version immediately. The container only reads the value the next
time it starts. After changing a secret, let the instance sleep, or redeploy
the image, before expecting the process to see it.

Local `wrangler dev` reads `cloudflare/backend/.dev.vars` (gitignored). Copy
`.dev.vars.example`.

The lab Cloudflare token is the Secrets Manager secret `cloudflare-api-token`
in `us-east-2`. The JSON keys are `CLOUDFLARE_API_TOKEN` and
`CLOUDFLARE_ACCOUNT_ID`. Do not print either value. The token used for this
preview can list Workers and container applications on the account. Confirm
with `npx wrangler whoami` before a deploy. User-token verify
(`/user/tokens/verify`) returns 401 for this account-owned token; that is
expected. Account verify succeeds.

Docker must be running. `wrangler deploy` builds the image and pushes it.
Containers are linux/amd64.

```bash
cd cloudflare/backend
npx wrangler deploy
```

First request after the first deploy can fail while Cloudflare provisions the
instance. `GET /health` should then return `{"status":"ok"}`.

## UI

vinext sits next to the existing Next.js scripts. `npm run dev` is still
`next dev`. Cloudflare uses the vinext scripts.

`vinext check` reported the App Router app, including `src/proxy.ts`, fully
supported. `ui/cloudflare.config.ts` is the Worker config (`cf` / vinext).
The API uses Wrangler because it is a Container project; do not run `cf deploy`
in `cloudflare/backend/`.

`NEXT_PUBLIC_*` values are inlined into the browser bundle at build time
(`ui/src/lib/api.ts`, `ui/src/lib/supabase/env.ts`). Set them in the
environment before `npm run deploy:vinext`. `ui/scripts/require-public-env.mjs`
refuses to build if any of the three is missing, and refuses a trailing slash
on the API URL. The Supabase URL and publishable key are the same values as
the Vercel project `lab-data-integrations-interface`. They are not in Secrets
Manager. Do not commit them. The API URL in `cloudflare.config.ts` must match
`NEXT_PUBLIC_API_URL`.

```bash
cd ui
export NEXT_PUBLIC_API_URL=https://ldi-api-preview.mind-technology-lab.workers.dev
export NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
export NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<publishable key>
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
npm ci
npm run deploy:vinext
```

The UI calls the API from the browser with the Supabase access token. It does
not send `X-Origin-Secret`. See the origin-secret row below.

## Environment variables

| Name | Who reads it | Wrangler | Required for |
|---|---|---|---|
| `CORS_ORIGINS` | `backend/main.py` | API var | Browser calls from the UI. Preview value includes the UI `workers.dev` origin and localhost. |
| `PORT` | uvicorn | Set by the container router to `8000` | Listen port. Not a secret. |
| `AWS_ACCESS_KEY_ID` | boto3, via `lib/aws/clients.py` | API secret | `/query` Athena and S3. From this environment's AWS credentials. |
| `AWS_SECRET_ACCESS_KEY` | boto3 | API secret | Same. |
| `AWS_SESSION_TOKEN` | boto3 | API secret, optional | Only for temporary credentials. Unset for the long-lived key. |
| `OPENAI_API_KEY` | `EnvVarsContainer` in `lib/load_env_vars.py` | API secret | SQL generation on `/query`. Secrets Manager `openai-api-key`, key `OPENAI_API_KEY`. |
| `SUPABASE_URL` | `backend/auth.py` | API secret | Verifying the bearer token on `/query`. Same host as `NEXT_PUBLIC_SUPABASE_URL`. |
| `GMAIL_SENDER_EMAIL` | `backend/agentic_search/mail.py` | API secret | Mailing `/query` results. Not in Secrets Manager or this environment. |
| `GMAIL_APP_PASSWORD` | `backend/agentic_search/mail.py` | API secret | Same. |
| `ORIGIN_SECRET` | `backend/origin.py` | API secret, optional | When set, requests other than `/health` need header `X-Origin-Secret`. Unset on the preview. |
| `OTEL_EXPORTER_OTLP_HEADERS` | `backend/telemetry/setup.py` | API secret, optional | Grafana. Unset means telemetry is off. |
| `MAIL_TEST_RECIPIENT` | mail smoke tests | API secret, optional | Not used by the server. |
| `NEXT_PUBLIC_API_URL` | `ui/src/lib/api.ts` | Build env, and a text binding on the UI Worker | Where the browser sends `/query`. |
| `NEXT_PUBLIC_SUPABASE_URL` | `ui/src/lib/supabase/env.ts` | Build env | Login and session. |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | `ui/src/lib/supabase/env.ts` | Build env | Login and session. |
| `CLOUDFLARE_API_TOKEN` | Wrangler / `cf` | Shell only | Deploy. Not an app variable. |
| `CLOUDFLARE_ACCOUNT_ID` | Wrangler / `cf` | Shell only | Deploy. Not an app variable. |

`ORIGIN_SECRET` used to be injected by CloudFront so browsers never saw it
(`docs/runbooks/HOW_TO_ENABLE_DDOS_PROTECTION.md`). The UI still does not send
`X-Origin-Secret`. On Cloudflare the Worker URL is the public origin, so
setting the secret without an injector makes `/query` return 403
`{"detail":"Forbidden"}` for the UI, including CORS preflight. Leave it unset
until that injector exists. `/health` stays exempt either way. A missing
bearer token is 401 `{"detail":"Not authenticated"}`, from `HTTPBearer` in
`backend/auth.py`. A bad token is 401 `{"detail":"Invalid access token"}`.

Region, bucket, Glue database, and Athena workgroup are constants in code
(`us-east-2`). They are not env vars.

## Verifying

`workers.dev` rejects the default Python user agent. The smoke script sets
one.

```bash
python scripts/cloudflare_smoke.py \
  --api-url https://ldi-api-preview.mind-technology-lab.workers.dev \
  --ui-url https://ldi-ui-preview.mind-technology-lab.workers.dev
```

It checks:

1. `GET /health` returns `{"status":"ok"}`.
2. `POST /query` with no credentials returns 401 `Not authenticated` when
   the origin guard is open. `403 Forbidden` means `ORIGIN_SECRET` is set.
3. `POST /query` with `Authorization: Bearer not-a-jwt` returns 401 once
   `SUPABASE_URL` is set. That path does not touch S3. A real S3 round trip
   needs a signed-in Supabase user; the script does not have one.
4. `OPTIONS /query` from the UI origin echoes that origin.
5. The UI URL returns 200 and the page title or the sign-in copy.

## What can be removed later

Do not delete these until the replacement is the one Mark uses.

| Path | Remove when |
|---|---|
| `railway/backend.json` | The API Container is the backend you use, and nothing still points Railway at this file. |
| `docs/runbooks/HOW_TO_DEPLOY_BACKEND_TO_RAILWAY.md` | Same. The file still says the backend only serves `/health` and needs no AWS credentials. The code has `/query`. |
| `docs/runbooks/HOW_TO_DEPLOY_UI_TO_VERCEL.md` | The UI Worker replaces the Vercel project. |
| `railway/bluesky_ingestion_jetstream.json` | Jetstream is retired, or it has its own Container. |
| `docs/runbooks/HOW_TO_DEPLOY_JETSTREAM_TO_RAILWAY.md` | Same. |
| `railway/bluesky_backfill_app/.railway/` | Backfill is retired, or it has its own Container. |
| `docs/runbooks/HOW_TO_DEPLOY_BACKFILL_TO_RAILWAY.md` | Same. |
| `docs/runbooks/HOW_TO_ADD_PREVIEW_BUILD_CHECKS_RAILWAY` | Nothing deploys to Railway. |
| `terraform/backend_edge/` | CloudFront in front of Railway is retired. The origin secret's injector lived here. |

## Open questions

- Should the UI Worker inject `X-Origin-Secret` on the way to the API, or
  should `ORIGIN_SECRET` stay unset now that CloudFront is not in front?
- Should Jetstream and the backfill worker be started as always-on
  Containers? They write production S3 and DynamoDB, and each is an always-on
  bill.
- Is `standard-1` enough once a real `/query` runs, or should the API move to
  `standard-2`?
- Should the API cron stay off (scale to zero, cold starts) or ping `/health`
  so the instance never sleeps?
- Where should `GMAIL_SENDER_EMAIL` and `GMAIL_APP_PASSWORD` live? They are
  not in Secrets Manager.
- The Supabase publishable settings live on the Vercel project, not in
  Secrets Manager. Should they move?
- Preview `workers.dev` URLs are public. Do they need Cloudflare Access?
- The image installs the whole root `uv.lock`, including packages the API
  process does not import (spaCy, scikit-learn, Prefect). Slimming that
  install would shorten cold starts. It is a separate change from the Railway
  install.
