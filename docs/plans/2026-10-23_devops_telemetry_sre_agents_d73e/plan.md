# DevOps, telemetry, and SRE agents

CI on `main` lints the repo and runs `pytest`. The same workflow does not deploy the app, smoke the UI after a deploy, or alert when Jetstream stalls, when backfill stalls, or when query spend jumps. The pages in this folder are the work that closes those gaps, checked against the repo on 2026-10-23.

The plan is documentation only. It does not change workflows, Terraform, application code, or secrets. [DevOps](devops.md) is the deploy and guardrail list. [Telemetry](telemetry.md) is the signals and alerts. [SRE agents](sre_agents.md) is the automation design, including five draft playbooks. The playbook text is in [draft_prompts/](draft_prompts/) and is not wired to Cursor Automations.

## What is true on main

[`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml) is the only GitHub Actions workflow. GitHub runs it on a push to `main` or `master`, and on every pull request. The `lint` job runs `uv run pre-commit run --all-files`. The step name lists ruff, ruff-format, pyright, complexipy, vulture, biome, and doctoc. The `test` job runs `uv run pytest tests/`. The workflow file has no `schedule` trigger, no deploy job, and no smoke job. The Cloudflare draft branch has the same single workflow.

[`docs/runbooks/HOW_TO_ADD_OBSERVABILITY_GRAFANA.md`](../../runbooks/HOW_TO_ADD_OBSERVABILITY_GRAFANA.md) describes OpenTelemetry export from `backend/` and `bluesky_ingestion_jetstream/` to Grafana Cloud. Traces, logs, and metrics go to the Grafana Cloud OTLP gateway. Service names and endpoints are constants in `backend/telemetry/constants.py` and `bluesky_ingestion_jetstream/telemetry/constants.py`. `OTEL_EXPORTER_OTLP_HEADERS` is the credential, and `setup_telemetry()` returns early when the variable is unset. The runbook tells you to put the variable in the root `.env` for a local run, and in each Railway service's variables. [`.env.example`](../../../.env.example) has a placeholder, not a live token. Git does not show whether the Railway projects currently have the variable set.

`bluesky_backfill_app/telemetry/` exports traces, logs, and metrics the same way. `bluesky_backfill_app/fetch_repos/main.py` calls `setup_telemetry()`, and [`docs/runbooks/HOW_TO_DEPLOY_BACKFILL_TO_RAILWAY.md`](../../runbooks/HOW_TO_DEPLOY_BACKFILL_TO_RAILWAY.md) documents the same header. The Grafana runbook's wording names the backend and Jetstream only. [Issue #165](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/165) is still open. The issue asks for backfill logs, a dashboard, queue depth, throughput, failures, and merge-job health. The code already records buffer bytes, queue depth, in-flight messages, peak RSS, rows, bytes, repos landed, flush failures, and repo failures. The repo has no backfill dashboard JSON. The checked-in dashboards are `bluesky_ingestion_jetstream/telemetry/dashboards/jetstream_ingestion.json` and `backend/telemetry/dashboards/agentic_search.json`.

Jetstream already exports `bluesky_jetstream.cursor.timestamp` (unix seconds of the cursor last written to DynamoDB), `bluesky_jetstream.connected`, flush row and byte counters, connection failures, dead letters, and dropped rows. [`docs/runbooks/HOW_TO_SETUP_JETSTREAM_DASHBOARD.md`](../../runbooks/HOW_TO_SETUP_JETSTREAM_DASHBOARD.md) imports that dashboard into Grafana Cloud. A separate cursor-age series is not in the code. You can alert on age by subtracting the timestamp gauge from the current time, once the gauge is actually reaching Grafana. Jetstream does not export RSS. Backfill does.

The local Grafana demo is `telemetry/app/`, with `docker-compose.yml` sending OTLP to an `otel-lgtm` container. [`docs/runbooks/lgtm-stack-setup.md`](../../runbooks/lgtm-stack-setup.md) and [`docs/runbooks/demo-app-usage.md`](../../runbooks/demo-app-usage.md) and [`docs/runbooks/demo-app-setup.md`](../../runbooks/demo-app-setup.md) describe it. `telemetry/app/README.md` is empty.

`terraform/` on `main` is AWS only:

| Directory | What it creates | Provider |
| --- | --- | --- |
| `terraform/backend_edge/` | CloudFront and a WAF in front of the Railway backend | `hashicorp/aws` and `hashicorp/random` |
| `terraform/bluesky_backfill_app/` | DynamoDB tables and the SQS queue plus dead-letter queue | `hashicorp/aws` |
| `terraform/bluesky_ingestion_jetstream/` | S3, Glue, the cursor table, the maintenance Athena workgroup, Step Functions, the schedule, and the maintenance alarm | `hashicorp/aws` |
| `terraform/data_platform/` | The data platform bucket, Glue database, and two Athena workgroups | `hashicorp/aws` |

[PR #242](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/242) merged on 2026-10-19. The title is "Protect the backend from DDoS with CloudFront and AWS WAF", and `terraform/backend_edge/` is that change. The maintenance workgroup sets `publish_cloudwatch_metrics_enabled = true`. Neither data platform workgroup sets a per-query scan cutoff, and neither sets that metrics flag. No Cloudflare resources are in Terraform on `main`.

Railway is still the production path in the runbooks on `main` (`HOW_TO_DEPLOY_BACKEND_TO_RAILWAY.md`, `HOW_TO_DEPLOY_JETSTREAM_TO_RAILWAY.md`, `HOW_TO_DEPLOY_BACKFILL_TO_RAILWAY.md`, `HOW_TO_DEPLOY_UI_TO_VERCEL.md`). [Issue #192](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/192) is open and asks to move Railway config-as-code to infrastructure as code. The issue stays relevant until Railway is actually retired.

On `main`, `bluesky_ingestion_jetstream/constants.py` sets `MAX_BUFFER_SIZE_BYTES` to 2 GiB of serialized JSON.

## What depends on the open Cloudflare drafts

[PR #245](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/245) is an open draft. The branch is `cursor/cloudflare-deploy-f070`, based on `main`. The title is "Cloudflare preview for the API, UI, Jetstream, and backfill". None of `cloudflare/`, `scripts/cloudflare_smoke.py`, or `docs/runbooks/HOW_TO_DEPLOY_TO_CLOUDFLARE.md` is on `main`.

[PR #247](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/247) is an open draft stacked on #245. The branch is `cursor/slim-api-image-f070`. The title is "Slim the Cloudflare container images". The diff gives Jetstream and backfill their own Dockerfiles and points each wrangler `image` at `./Dockerfile`. It also installs `pyjwt[crypto]` so the API image can parse ES256 tokens. #247 does not change the observability blocks or `scripts/cloudflare_smoke.py`.

On the #245 branch, `cloudflare/backend/wrangler.jsonc`, `cloudflare/jetstream/wrangler.jsonc`, and `cloudflare/backfill/wrangler.jsonc` each set `observability.logs` and `observability.traces` with `head_sampling_rate` 1. Cloudflare documents that value as 100 percent of requests ([Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)). Each container sets `observability.enabled` to true. The Worker names are `ldi-api-preview`, `ldi-jetstream-preview`, and `ldi-backfill-preview`, with `workers_dev: true`. There is no separate production environment in those files.

The wrangler files do not set a log retention period. Cloudflare's Workers Logs limit is 7 days on the Paid plan and 3 days on the Free plan, on the same page. Git does not say which plan the account is on. Workers Logs pricing on that page changes on 2026-12-01, which is the date in the telemetry notes for avoiding Cloudflare log storage.

Each container's `src/index.ts` forwards `OTEL_EXPORTER_OTLP_HEADERS` into the process when the Worker value is a non-empty string. The deploy runbook lists the variable as an optional secret on the API, Jetstream, and backfill Workers, and says an unset value leaves telemetry off. `.dev.vars.example` leaves the line commented. Git does not show the live secret.

`scripts/cloudflare_smoke.py` is a manual command. The deploy runbook tells you to run it. CI does not. The script checks all of the following:

1. `GET /health` returns `{"status":"ok"}`.
2. `POST /query` with no credentials returns 401 `Not authenticated` when the origin guard is open. `403 Forbidden` means `ORIGIN_SECRET` is set.
3. `POST /query` with a bogus bearer returns 401 `Invalid access token` once `SUPABASE_URL` is set, or 403 when the origin guard rejects the call first.
4. `OPTIONS /query` from the UI origin echoes that origin.
5. `GET` on the UI with no Access token redirects to a `cloudflareaccess.com` host.
6. With `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET`, or with those fields in Secrets Manager `lab-data-integrations-access-smoke`, `GET /` and `GET /login` return 200 and the Supabase sign-in form. `Internal Server Error` fails the check. Missing Access credentials fail the script. They do not count as a pass.
7. When `SUPABASE_TEST_EMAIL` and `SUPABASE_TEST_PASSWORD` are set, the script signs in and `POST /query` must return 202. Without those two variables the script prints a skip. The skip is not a failure. No test user is stored in the repo.

`cloudflare/access/apply_preview_access.py` on the same branch creates the preview Access applications and the service token `ldi-preview-smoke`. The script is not Terraform, and it is not on `main`. `/health` and `/query` are public paths on the API application. Jetstream and the backfill worker are outside that Access config.

On the #245 branch the flush cap is 128 MiB. The comment in `bluesky_ingestion_jetstream/constants.py` says a 2 GiB JSON cap filled RAM on the 4 GiB preview instance and the kernel killed the process (exit 137) before a flush. That lower cap is not on `main`.

The #245 description also records three other preview failures. A UI request returned 500 because `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` were not Worker text bindings. The Secrets Manager URL had been a CloudFront host and was put back to the Supabase project host. A real sign-in then failed in the API log because PyJWT could not parse an ES256 key without the `cryptography` package. #247 is the image change for that package. None of those fixes are on `main`.

`Container.start()` from `@cloudflare/containers` probes a TCP port. The Jetstream and backfill processes do not listen, and the probe can abort the Durable Object. The #245 Workers call `ctx.container.start()` and do not probe. That code is only on the draft branch.

Nothing in the repo starts a backfill run on deploy. On the draft, `POST /start` requires `BACKFILL_TRIGGER_TOKEN`. Whether anyone has completed a backfill run on the preview is not in git.

[PR #220](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/220) is an open pull request titled "Backfill iceberg moving cron". It is not an issue. The weekly merge state machine is not in `terraform/` on `main`. The design is [`docs/design_docs/2026-09-19_bluesky_backfill_merge.md`](../../design_docs/2026-09-19_bluesky_backfill_merge.md).

[Issue #189](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/189) is open and asks for a Grafana view of agentic query health. `backend/telemetry/dashboards/agentic_search.json` already queries Tempo spans named `agentic_search.query` and splits outcomes `results`, `invalid`, `mail_failed`, `rejected`, and `failed`. `backend/agentic_search/handle_query.py` sets `outcome`, including `mail_failed`. The repo has no metric for Athena bytes scanned, OpenAI token cost, or a refusal-reason counter. Auth rejection is a log line in `backend/auth.py` (`rejected access token`), not a counter.

## Where the source notes were off

The notes were right about CI having no deploy, no smoke, and no schedule, and about Grafana Cloud plus the `telemetry/` demo. The checks above change these points:

- `OTEL_EXPORTER_OTLP_HEADERS` is not "set only on Railway". Local `.env` is part of the runbook. Live Railway values are still not visible in git.
- Backfill already has an OTel exporter. #165 is still open for the dashboard and the merge-job view.
- Jetstream already exports cursor timestamp, connection state, and flush size. Search already has a trace dashboard. The new-metric list in [telemetry](telemetry.md) names only the gaps.
- The smoke script is not on `main`. On #245 it checks health, missing and bogus bearers, CORS, the Access redirect, the signed-in UI, and an optional signed-in `/query`. It does not fail when the Supabase test user is unset.
- "Logs stay in Cloudflare 7 days" is a Paid-plan limit, not a setting in wrangler. The Free-plan limit is 3 days. The account plan is unverified.
- The draft container code does forward `OTEL_EXPORTER_OTLP_HEADERS` when the Worker secret is set. Whether Grafana is receiving container telemetry is still unverified.
- Terraform names are the directory names above, not short names `backfill` and `jetstream`. Access is a Python script on #245, not Terraform.
- #242 is merged. #220 is a pull request. #245 and #247 are open drafts, and only #245 carries observability and the smoke script.
- The pre-commit step also runs ruff-format, complexipy, vulture, and doctoc.
- The 2 GiB flush cap is `main`. The 128 MiB cap and the 4 GiB OOM note are on #245 only.
- #245 does not define separate preview and production wrangler environments. Every Worker there is a preview name.
- The Oct 14 10x data-cost figure and the $50 to $100 backfill enqueue are in the source notes. The repo has no bill to check them against.

## Recent failures the plan is answering

A 2 GiB JSON flush cap filled the 4 GiB Jetstream preview and the process was killed before a flush. #245 lowers the cap to 128 MiB, and `main` still has the 2 GiB cap. The port probe aborted the Durable Object because the container process does not listen. The UI returned 500 when the Supabase URL and publishable key were missing as Worker bindings. The Secrets Manager URL had been a CloudFront host. The API rejected a real Supabase session because the image lacked `cryptography` for ES256. A backfill run is not started by deploy. The first two deploy items in [DevOps](devops.md) are meant to fail the deploy on the UI 500 and the rejected session, which checks that stop at the Access wall do not see.

## Order to do the work

1. Send Cloudflare logs and traces to Grafana with `persist: false`, set the container OTel secret, and add three synthetic checks. One of the checks is authenticated with a test Supabase user. The source notes marked this small to medium. It depends on #245 landing, or on an equivalent wrangler config on `main`.
2. Add the deploy workflow, the config check, smoke in that workflow, and a single rollback command. The source notes marked the step medium, and said it would have caught three of the six failures: the missing Supabase bindings that returned UI 500, the Supabase URL whose host was CloudFront, and the real session rejected for lack of ES256 support. The OOM, the port probe, and an unrun backfill need the container smoke in [DevOps item 3](devops.md#3-container-startup-and-memory-smoke).
3. Add the first alerts (Jetstream cursor age, RSS, and OOM, HTTP 5xx, synthetic checks, email failures, budgets, and an Athena scan limit) and two report-only automations (deploy smoke failed, and the daily digest). The source notes marked this small to medium.

## Related work

- [Issue #165](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/165), backfill telemetry dashboard.
- [Issue #189](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/189), agentic search observability.
- [Issue #192](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/192), Railway config-as-code to infrastructure as code.
- [PR #220](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/220), backfill Iceberg merge cron, still open.
- [PR #242](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/242), CloudFront and WAF, merged.
- [PR #245](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/245), Cloudflare preview, open draft.
- [PR #247](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/247), slimmer container images, open draft stacked on #245.

## Not verified

- Whether the Cloudflare account is on the Paid plan, which decides 7-day versus 3-day Workers Logs retention.
- Whether the live Railway services, or the live Cloudflare Worker secrets, currently have `OTEL_EXPORTER_OTLP_HEADERS` set, and whether any container export has arrived in Grafana.
- Whether a person has run a backfill on the preview.
- The Oct 14 10x data-cost figure and the $50 to $100 backfill enqueue from the source notes.
- Whether Cloudflare "Monitors" SQL alerts are available on the account.
- Whether Cloudflare Health Checks work on `workers.dev`.
- Whether `wrangler rollback` rolls back container images or only the Worker script.
- Cursor Bugbot pricing. The product page is [Bugbot](https://cursor.com/bugbot).
- The dollar threshold for Athena spend per day. The source notes left it as `$X`.
- Whether a Grafana MCP server is already connected for this repo. The repo does not configure one.
