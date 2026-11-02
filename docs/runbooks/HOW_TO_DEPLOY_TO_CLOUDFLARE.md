# How to Deploy to Cloudflare

## Overview

The FastAPI backend runs as a Cloudflare Container. The Next.js UI in `ui/`
runs as a Cloudflare Worker, built with vinext. Jetstream runs as its own
always-on Container. The backfill fetch worker runs as its own Container that
you start when you want a run. Object storage stays on AWS S3. This deploy
does not use Cloudflare R2.

| | |
|---|---|
| API config | `cloudflare/backend/wrangler.jsonc` |
| API image | `cloudflare/backend/Dockerfile` (build context is the repo root). Syncs groups `api`, `ml`, and `ingestion`. |
| Jetstream image | `cloudflare/jetstream/Dockerfile`. Syncs group `ingestion`. |
| Backfill image | `cloudflare/backfill/Dockerfile`. Syncs group `backfill`. |
| API start | `uvicorn backend.main:app --host 0.0.0.0 --port 8000` |
| API Worker name | `ldi-api-preview` |
| Jetstream config | `cloudflare/jetstream/wrangler.jsonc` |
| Jetstream start | `python -m bluesky_ingestion_jetstream.main` |
| Jetstream Worker name | `ldi-jetstream-preview` |
| Backfill config | `cloudflare/backfill/wrangler.jsonc` |
| Backfill start | `python -m bluesky_backfill_app.fetch_repos.main` |
| Backfill Worker name | `ldi-backfill-preview` |
| UI config | `ui/cloudflare.config.ts` |
| UI deploy | `npm run deploy:vinext` from `ui/` |
| UI Worker name | `ldi-ui-preview` |
| Account | `CLOUDFLARE_ACCOUNT_ID` from Secrets Manager. Do not commit it. |
| Subdomain | `mind-technology-lab.workers.dev` |

Jetstream and the backfill worker each have their own image. They do not
install the API's FastAPI or model packages. The backfill image also skips
PyIceberg. Local `uv sync` still installs every group.

Preview URLs, once deployed:

- API: `https://ldi-api-preview.mind-technology-lab.workers.dev`
- UI: `https://ldi-ui-preview.mind-technology-lab.workers.dev`
- Jetstream status: `https://ldi-jetstream-preview.mind-technology-lab.workers.dev/status`
- Backfill status: `https://ldi-backfill-preview.mind-technology-lab.workers.dev/status`

These names are the live `workers.dev` hostnames. "preview" means the first
Cloudflare host, not a git preview environment. A later cutover can rename
them to `ldi-api`, `ldi-ui`, `ldi-jetstream`, and `ldi-backfill`. That rename
changes the public hosts, the Access applications, and the UI API URL, so
this document keeps the current names. They are not a production cutover.
The UI and API `workers.dev` URLs are meant to sit behind Cloudflare
Access. Access is not on yet. See [Cloudflare Access](#cloudflare-access).

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

Jetstream and the backfill fetch worker are the same kind of process. Each
one is an infinite loop (a WebSocket firehose, an SQS long poll). Each has
its own Container and `max_instances: 1`. They are not on the API container.
A shared process would tie the firehose to the API's 30 minute sleep, and a
second copy of Jetstream would write the production bucket twice.

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

Jetstream and the backfill worker do not listen on a port. Both Workers
call `ctx.container.start()` and skip the TCP probe inside
`Container.start()` from `@cloudflare/containers`. That probe aborts the
Durable Object when its last error is `Network connection lost`. The first
start still spends its time pulling the image.

### Instance lifetime and sleep

One Durable Object name, `api`, plus `max_instances: 1`, keeps a single API
container. `sleepAfter` is `30m`. Cloudflare resets that timer when the Worker
proxies an HTTP request through to the container. Billing for the instance
stops when it sleeps. Disk is ephemeral and is wiped on sleep, which is fine:
tables live in S3 and Glue, and the rate-limiter state is allowed to reset.

`/query` returns 202, and the rest of the work continues inside the process
as a background task. That background work does not reset the sleep timer.
If a query runs longer than 30 minutes, and no other proxied request arrives
during those 30 minutes, Cloudflare stops the container while the query is
still running. The caller already has the 202. The Athena query, the model
call, or the email can be cut off in the middle.

There is no cron that fetches `/health` to keep the API awake. Leave it that
way. A keep-warm cron would bill the API as an always-on instance.

Cloudflare can still restart the host. The container gets SIGTERM, then about
15 minutes before SIGKILL. The Jetstream and backfill processes already
handle SIGTERM. See the sections below for what each one does with that
signal.

### Instance size

The API, Jetstream, and the backfill worker all use `standard-1` for now.
That size is 1/2 vCPU, 4 GiB of memory, and 8 GB of disk. The previous shared
image was 3.77 GB. After the dependency split, `docker images` reports the
API image at 1.31 GB, Jetstream at 1.16 GB, and the backfill image at 908 MB.
Each one fits on the `standard-1` disk with room for the writable layer.
`basic` has 1 GiB of memory, which is still too small for these processes.
`lite` has 256 MiB of memory and 2 GB of disk.

Instance types, from the Containers limits page as of 2026-10-21:

| Instance type | vCPU | Memory | Disk |
|---|---|---|---|
| `lite` | 1/16 | 256 MiB | 2 GB |
| `basic` | 1/4 | 1 GiB | 4 GB |
| `standard-1` | 1/2 | 4 GiB | 8 GB |
| `standard-2` | 1 | 6 GiB | 12 GB |
| `standard-3` | 2 | 8 GiB | 16 GB |
| `standard-4` | 4 | 12 GiB | 20 GB |

`dev` is an alias of `lite`. `standard` is an alias of `standard-1`. The
image has to be smaller than the instance disk.

Stay on `standard-1` until one of these shows up, then change
`instance_type` in the Wrangler config and redeploy that Worker.

- Memory. The process is killed while Python is still importing, the
  container exits with code 137, or the logs say the process ran out of
  memory. Move to `standard-2` (1 vCPU, 6 GiB, 12 GB disk).
- CPU. The 1/2 vCPU stays busy for a long stretch during `/query`, or the
  Jetstream cursor in DynamoDB falls further behind while the process is up.
  The cursor falling behind means the process cannot flush as fast as events
  arrive. Move to `standard-2`, then `standard-3`, then `standard-4` if it
  is still behind.
- Disk. The image no longer fits, or the container runs out of disk while
  it writes a temporary file. `standard-2` has 12 GB of disk. The image
  limit is the disk size.

### Cost

Containers require the Workers Paid plan ($5 per month per account, if the
account is not already paying it). Included each month: 25 GiB-hours of
memory, 375 vCPU-minutes, 200 GB-hours of disk. Past that, memory is
$0.0000025 per GiB-second, CPU is $0.000020 per active vCPU-second, and disk
is $0.00000007 per GB-second. Egress in North America and Europe is $0.025
per GB after 1 TB. Figures are from the Containers pricing page as of
2026-10-05 and the limits page as of 2026-10-21.

`standard-1` left running all month is about 4 GiB times 730 hours. Memory
overage is about $26. Disk overage on the 8 GB volume is about $1.40. CPU is
billed on active use, not on the 1/2 vCPU reservation. An idle process is a
few dollars. A pegged 1/2 vCPU adds about $25. One always-on `standard-1` is
roughly $35 to $60 per month on top of the plan, before logs and before
egress from the container out to AWS.

Jetstream is the always-on container, so that $35 to $60 is the Jetstream
line. The firehose spends much of its time waiting on the socket, so the CPU
part can land under the pegged figure. Uploads to S3 are egress on top of
that range.

The API scales to zero. One 30-minute wake per day for a month is about 60
GiB-hours, near $0.30 of memory past the included 25, plus the plan. Real
`/query` traffic adds a wake for each quiet stretch longer than 30 minutes.
The UI Worker for this lab's traffic fits in the paid request allotment.

The backfill worker bills only while a run you started is up. A few hours is
well under a dollar at these rates. A run stops when the queue drains or you
post `/stop`, so a run you forget with work left costs the same as Jetstream.

### Jetstream

Jetstream is its own Container, Worker name `ldi-jetstream-preview`, Durable
Object name `jetstream`, `max_instances: 1`, instance type `standard-1`. The
command is `python -m bluesky_ingestion_jetstream.main`. The Worker forwards
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optionally
`AWS_SESSION_TOKEN`, plus `DEPLOYMENT_ENVIRONMENT` and
`OTEL_RESOURCE_ATTRIBUTES`. When `OTEL_EXPORTER_OTLP_HEADERS` is absent, the
process reads it from Secrets Manager
`lab-data-integrations-interface-grafana-cloud-oltp-header`. Region, bucket,
Glue, and the cursor table are constants in code. The cursor table is
`bluesky_jetstream_cursor`, and the item key is `stream_id` =
`bluesky_jetstream`.

Two timers can stop the process. Both are set so a healthy writer stays up,
and the container is billed the whole time it stays up.

`JetstreamContainer.onActivityExpired` leaves the process running. The
library's default for that hook sends SIGTERM when `sleepAfter` elapses.
`sleepAfter` here is `30m`. Proxied HTTP is what resets the library timer,
and this process does not serve HTTP. With the default hook, the process
would stop about 30 minutes after the last refresh. The override is what
keeps that hook from sending SIGTERM.

Cloudflare also stops a container shortly after its Durable Object goes
idle, unless the object calls `setInactivityTimeout`. The platform cap on
that call is 6 hours. The first preview start was stopped this way, about 6
minutes after boot, while the library hook had not fired. `supervise` calls
`container.setInactivityTimeout` for 6 hours whenever the process is
running. The constructor calls it again when the Durable Object restarts and
the container is already running, because the timeout does not survive that
restart.

`supervise` starts the process with `ctx.container.start()`. It does not use
`Container.start()` from `@cloudflare/containers`. That method probes a TCP
port, and this process does not listen. When the probe's last error is
`Network connection lost`, the library aborts the Durable Object. The
preview then has no container instance, and later start attempts fail with
`no container instance` until the platform hands one out again. `running` on
`GET /status` is `ctx.container.running`. A lost connection while the
instance still looks running is destroyed so the next minute can start a
new one. `monitor()` logs the exit.

A cron of `* * * * *` on the Worker calls `supervise` inside the Durable
Object. When `JETSTREAM_ENABLED` is the string `true`, supervise starts the
process if it is down. If the process is already up, supervise sets the 6
hour platform timeout again. When the var is any other value, supervise
sends SIGTERM if the process is up. If the cron stays down for the full 6
hours, the platform timeout elapses and Cloudflare sends SIGTERM. The cron
is how a dead process gets restarted, and it is how you turn the writer off.
The API Worker does not have this cron.

Cloudflare sends SIGTERM when it stops the instance, including a host move
and an image rollout. It waits about 15 minutes, then sends SIGKILL.
`bluesky_ingestion_jetstream/main.py` turns SIGTERM into `KeyboardInterrupt`,
logs `stopped`, and flushes telemetry. It does not flush the in-memory
buffers on that path. The DynamoDB cursor stays at the last successful
flush. The next process reads the firehose again from that cursor. If
`JETSTREAM_ENABLED` is still `true`, the supervisor starts that next process
within about a minute.

`GET /status` returns JSON `{"enabled": true, "running": true}` and does not
start or stop the process. There is no public start or stop route.

Before you let it start, confirm that no other Jetstream writer is
committing. A live writer updates `updated_at` on the cursor item at least
every 30 minutes while events are arriving (`MAX_BUFFER_AGE_SECONDS` in
`bluesky_ingestion_jetstream/constants.py`). It updates sooner when the
buffers reach `MAX_BUFFER_SIZE_BYTES` (128 MiB of serialized JSON). That
cap used to be 2 GiB. On the 4 GiB `standard-1` instance, a replay from an
old cursor grew the process to about 2.2 GiB of resident memory in four
minutes and then the kernel killed it with exit 137, before a flush. The
smaller cap is what lets that instance commit during catch-up.

`supervise` also runs `exec` on the container and logs whether pid 1 is the
Jetstream module and that process's resident memory in kilobytes. It does
not log the command line or the environment.

To see whether a writer has committed, read `updated_at` on the cursor item
in `us-east-2`:

```bash
aws dynamodb get-item \
  --region us-east-2 \
  --table-name bluesky_jetstream_cursor \
  --key '{"stream_id":{"S":"bluesky_jetstream"}}' \
  --consistent-read \
  --projection-expression "updated_at"
```

If `updated_at` is newer than about 30 minutes, another writer is committing.
Also list container applications and confirm you do not already have a
Jetstream container running. The cursor is the record that a writer
committed.

If you cannot confirm the cursor is idle, deploy with the writer held.
A secret cannot use the name `JETSTREAM_ENABLED`. That name is already the
var, and Cloudflare returns error 10053. This deploy does not rebuild the
image. `--durable-objects-code-update-mode immediate` makes the running
object read the new value. Without it, `GET /status` can keep reporting the
old value.

```bash
cd cloudflare/jetstream
npx wrangler deploy --containers-rollout none \
  --var JETSTREAM_ENABLED:false \
  --durable-objects-code-update-mode immediate
```

Wait until `GET /status` reports `"enabled": false` and `"running": false`.
Use a browser User-Agent. workers.dev rejects the default Python user agent
with error 1010. To turn the writer back on, deploy again without the var
override. The value in `wrangler.jsonc` is `true`.

```bash
npx wrangler deploy --containers-rollout none \
  --durable-objects-code-update-mode immediate
```

Wait until `GET /status` reports `"enabled": true` and `"running": true`.
The new process reads `bluesky_jetstream_cursor` and resumes from it. The
process keeps the environment from that start until the next start.

Deploy from `cloudflare/jetstream/` with `CLOUDFLARE_API_TOKEN` and
`CLOUDFLARE_ACCOUNT_ID` exported. Pass the AWS keys in a secrets file so the
first start has them. Do not print the file.

```bash
cd cloudflare/jetstream
npx wrangler deploy --secrets-file /path/to/jetstream.secrets.env
```

The file is `KEY=value` lines for `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` only. After the first deploy, the cron starts the
process within a minute when `JETSTREAM_ENABLED` is `true`. The first start
includes the image pull. `GET /status` then reports `running: true`, and
`updated_at` on the cursor moves after the next flush.

### Backfill

The backfill fetch worker is its own Container, Worker name
`ldi-backfill-preview`, Durable Object name `backfill`, `max_instances: 1`,
instance type `standard-1`. The command is
`python -m bluesky_backfill_app.fetch_repos.main`. The Worker starts that
command with `ctx.container.start()` and does not probe a port. The Worker
forwards `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optionally
`AWS_SESSION_TOKEN`, plus `DEPLOYMENT_ENVIRONMENT` and
`OTEL_RESOURCE_ATTRIBUTES`. When `OTEL_EXPORTER_OTLP_HEADERS` is absent, the
process reads it from Secrets Manager
`lab-data-integrations-interface-grafana-cloud-oltp-header`. The queue name
and the DynamoDB tables are constants in code. It does not need to stay up.
You start a run when you
want one.

Nothing in this repo starts a run on deploy. `POST /start` and `POST /stop`
require `Authorization: Bearer` matching the Worker secret
`BACKFILL_TRIGGER_TOKEN`. The comparison is timing-safe. If the secret is
unset or the header does not match, the Worker returns 401 and does not
start the process. The token is not copied into the container. `GET /status`
is public and returns `{"running": true}` or `{"running": false}` only.
`/status` does not start a run.

The Worker secret `BACKFILL_TRIGGER_TOKEN` must match the value in AWS Secrets
Manager secret `ldi-backfill-trigger-token` in `us-east-2`. Set the Worker
secret separately through the Cloudflare dashboard or Wrangler. The Worker
does not read this AWS secret automatically. After a rotation, update both.
Wrangler will not show the value back to you.

Before starting or stopping a run, read the token into the current shell.
This requires AWS credentials with `secretsmanager:GetSecretValue` on
`ldi-backfill-trigger-token`, the AWS CLI, and `jq`. The secret is a JSON
object with a `BACKFILL_TRIGGER_TOKEN` field. Do not print the value or run
these commands with shell tracing enabled.

```bash
set +x
BACKFILL_TRIGGER_TOKEN="$(aws secretsmanager get-secret-value \
  --region us-east-2 --secret-id ldi-backfill-trigger-token \
  --query SecretString --output text --no-cli-pager | \
  jq -er '.BACKFILL_TRIGGER_TOKEN | select(type == "string" and length > 0)')" || {
  unset BACKFILL_TRIGGER_TOKEN
  echo "Could not load the backfill token; do not start the run." >&2
}
```

Start a run:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer $BACKFILL_TRIGGER_TOKEN" \
  -H "User-Agent: ldi-backfill-trigger/1.0" \
  https://ldi-backfill-preview.mind-technology-lab.workers.dev/start
```

Stop a run:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer $BACKFILL_TRIGGER_TOKEN" \
  -H "User-Agent: ldi-backfill-trigger/1.0" \
  https://ldi-backfill-preview.mind-technology-lab.workers.dev/stop
```

After the operation, clear the shell variable with `unset BACKFILL_TRIGGER_TOKEN`.
The curl authorization header can be visible to other processes on the same
machine while curl runs; use a trusted workstation.

Check whether a run is up, without starting one:

```bash
curl -fsS \
  -H "User-Agent: ldi-backfill-trigger/1.0" \
  https://ldi-backfill-preview.mind-technology-lab.workers.dev/status
```

The first `/start` can take several minutes while Cloudflare pulls the image.
If the client gives up, check `/status` before you post `/start` again.

A run has no time limit. It ends in one of two ways: `POST /stop`, or the queue
draining. The worker treats the queue as drained after 10 minutes of empty polls
(`IDLE_EXIT_SECONDS`), once SQS also reports nothing waiting or in flight. It
then flushes and exits 0. A failed repo stays hidden in flight for up to an hour
before its retry, so the run waits for it.

A minute cron keeps a started run up. It calls `setInactivityTimeout`, because
Cloudflare otherwise stops the container shortly after the Durable Object goes
idle, and the cap on that timeout is 6 hours. It also restarts a process that
exited with any code but 0, such as a crash, an out-of-memory kill, or a host
restart. It never starts a run that `/start` did not ask for. Credentials that
fail at startup therefore restart every minute until you post `/stop`.

A forgotten run with work left keeps billing as an always-on `standard-1`.
Repos queued after a run drains wait for the next `/start`.

SIGTERM is what `/stop` sends. `bluesky_backfill_app/fetch_repos/main.py` turns
it into `KeyboardInterrupt`. The `run()` finally block flushes a remaining buffer
with reason `stop`, telemetry is flushed, and the process exits 143. Cloudflare
waits about 15 minutes after SIGTERM before SIGKILL, which covers that drain.

Deploy the Worker from `cloudflare/backfill/` the same way as Jetstream,
with an AWS secrets file, and without calling `/start`. Put
`BACKFILL_TRIGGER_TOKEN` only when you are about to run a backfill.

## What this deploy runs

| Service | Where it runs |
|---|---|
| FastAPI backend | Container `ldi-api-preview`. Scales to zero after 30 minutes. |
| Next.js UI | Worker `ldi-ui-preview` |
| Jetstream ingester | Always-on Container `ldi-jetstream-preview`. Writes the production bucket and the cursor table. |
| Backfill fetch workers | On-demand Container `ldi-backfill-preview`. A run starts only from `POST /start`, and ends on `POST /stop` or when the queue drains. |
| `gather_users` | Not part of this deploy. It stays a CLI. |
| `telemetry/app` | Not part of this deploy. It stays a sample app. |

## Backend

### Build context

Imports are absolute from the repo root (`from backend.main`, `from lib.aws`,
`from bluesky_ingestion_jetstream...`). One `pyproject.toml` / `uv.lock`
covers the repo. The image is built with the repo root as context
(`image_build_context` in the Wrangler config). `.dockerignore` keeps `.venv`,
git, and experiment data out of the context. The root `telemetry` sample app
is ignored as `/telemetry`, so the `telemetry` packages inside Jetstream and
the backfill app are still copied.

The API image runs `uv sync --frozen --no-dev --no-default-groups
--no-install-project` with groups `api`, `ml`, and `ingestion`. Jetstream
syncs `ingestion`. The backfill image syncs `backfill`. Packages stay on
`PYTHONPATH`. The API command is `uvicorn backend.main:app`.
A variable that is already present stays as it is, including an empty value.
`backend/main.py` calls `load_dotenv()`, which does not override those
variables, then `fill_unset_secrets()` in `lib/aws/secrets_env.py`. That
function reads Secrets Manager in `us-east-2` for any of these names that
are absent: `OPENAI_API_KEY`, `SUPABASE_URL`, `GMAIL_SENDER_EMAIL`,
`GMAIL_APP_PASSWORD`, and `OTEL_EXPORTER_OTLP_HEADERS`. Jetstream and the
backfill worker call it for the OTLP header only. It does not print values.
`EnvVarsContainer` then reads `OPENAI_API_KEY` from the environment.

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

Repeat for `AWS_SECRET_ACCESS_KEY` and, when the credentials are temporary,
`AWS_SESSION_TOKEN`. Do not put `OPENAI_API_KEY`, `SUPABASE_URL`,
`GMAIL_SENDER_EMAIL`, `GMAIL_APP_PASSWORD`, or `OTEL_EXPORTER_OTLP_HEADERS`
on the Worker. The process reads those from Secrets Manager when the name
is absent. `wrangler secret put` deploys a new Worker version immediately.
The container keeps the environment from the start that is already running.
After changing an AWS credential, let the instance sleep, or redeploy the
image, before expecting the process to see it. A rotated Secrets Manager
value is also picked up at the next process start.

`SUPABASE_URL` is the JSON field `NEXT_PUBLIC_SUPABASE_URL` in Secrets
Manager `lab-data-integrations-supabase-public`.
`scripts/set_api_supabase_url.py` checks that field, does not print it, and
does not store it on the Worker. It refuses a host that is not a
`supabase.co` project host. `backend/auth.py` verifies ES256 tokens
with PyJWT, which needs the `cryptography` package. `pyjwt[crypto]` in
`pyproject.toml` installs that package. Without it, a real Supabase token
is rejected with `Invalid access token` and the container log says
`ES256 requires 'cryptography' to be installed`.

`scripts/set_grafana_otlp_header.py` reads `OTEL_EXPORTER_OTLP_HEADERS` from
Secrets Manager `lab-data-integrations-interface-grafana-cloud-oltp-header`
in `us-east-2`. It does not print the value and it does not store the header
on a Worker. The process reads that field when the variable is absent. The
value has to start with `Authorization=Basic%20`. A raw space is refused,
because the Python exporter needs the space written as `%20`. The script
uses the header only for the destinations below. Run it from the repo root
with `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, and AWS credentials
for `us-east-2`.

The same script creates or updates two Workers observability destinations,
`ldi-preview-grafana-logs` and `ldi-preview-grafana-traces`, on the gateway
in `backend/telemetry/constants.py`. It then points the API, Jetstream,
backfill, and UI Workers at those destinations with `persist: false`, so
Cloudflare does not keep a second copy of Worker logs and traces. Container
stdout still goes to the containers dataset. The destination Authorization
header is the same credential with the `%20` decoded to a space.

The preview Wrangler configs also set `DEPLOYMENT_ENVIRONMENT` to
`cloudflare-preview` and `OTEL_RESOURCE_ATTRIBUTES` to
`deployment.environment=cloudflare-preview`. `build_resource` adds
`deployment.environment` when `DEPLOYMENT_ENVIRONMENT` is set. `Resource.create` also copies
`OTEL_RESOURCE_ATTRIBUTES`, which is how an image built before that Python
change still labels its signals. Those vars are not secrets. They are
applied by `wrangler deploy`, not by `wrangler secret put`.

`wrangler secret put` does not upload the Worker script and does not rebuild
the image. After changing a forwarded AWS credential or a Wrangler var,
deploy each container Worker with `--containers-rollout none` so the new
values are forwarded and the image that is already running stays in place:

```bash
cd cloudflare/backend
npx wrangler deploy --containers-rollout none
```

Repeat from `cloudflare/jetstream` and `cloudflare/backfill`. The container
still has the environment from the start that is already running. Restart
the API by requesting `GET /health` after its instance has stopped. Jetstream
does not sleep on its own. Hold it and start it again with the commands in
[Jetstream](#jetstream). The new process resumes from
`bluesky_jetstream_cursor`.

Local `wrangler dev` reads `cloudflare/backend/.dev.vars` (gitignored). Copy
`.dev.vars.example`. Jetstream and the backfill worker have their own
`.dev.vars.example` files.

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

Deploy Jetstream and the backfill worker from their own directories. Each
deploy builds that Worker's Docker file. Pass `--secrets-file` on the first
deploy so AWS credentials are present before the process starts. See
[Jetstream](#jetstream) and [Backfill](#backfill).

## UI

vinext sits next to the existing Next.js scripts. `npm run dev` is still
`next dev`. Cloudflare uses the vinext scripts.

`vinext check` reported the App Router app, including `src/proxy.ts`, fully
supported. `ui/cloudflare.config.ts` is the Worker config (`cf` / vinext).
The API uses Wrangler because it is a Container project; do not run `cf deploy`
in `cloudflare/backend/`.

The browser bundle inlines `NEXT_PUBLIC_*` at build time (`ui/src/lib/api.ts`,
`ui/src/lib/supabase/env.ts`). The prefix is the Next.js rule for a value
that ships in the browser bundle. vinext serves that bundle, and `npm run
build` is still `next build`. Dropping the prefix would leave the values
out of the bundle. `proxy.ts` reads the same names from
`process.env` on each request. With `nodejs_compat` and a compatibility date
after 2025-04-01, the Worker copies text bindings into `process.env`.
`cloudflare.config.ts` publishes the two Supabase names as text bindings.
They are not committed. A deploy that omits them returns plain text
`Internal Server Error` from `proxy.ts` before the page renders.

`npm run deploy:vinext` loads the names, then starts `vinext-cloudflare
deploy` in that same process. The loader refuses a trailing slash on
`NEXT_PUBLIC_API_URL`. When both Supabase names are unset, it reads
Secrets Manager secret `lab-data-integrations-supabase-public` in
`us-east-2`. It does not print the values. The Supabase URL host has to be
a `supabase.co` project host. One Supabase name without the other stops
the deploy. A missing secret stops the deploy and names the secret. The
API URL in `cloudflare.config.ts` has to match `NEXT_PUBLIC_API_URL`.

The reader uses boto3. It tries `PYTHON`, then the repo `.venv`, then
`python3`. AWS credentials for `us-east-2` have to be available the same
way the rest of this deploy reads Secrets Manager.

```bash
cd ui
export NEXT_PUBLIC_API_URL=https://ldi-api-preview.mind-technology-lab.workers.dev
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
npm ci
npm run deploy:vinext
```

The UI calls the API from the browser with the Supabase access token.

## Environment variables

| Name | Who reads it | Wrangler | Required for |
|---|---|---|---|
| `CORS_ORIGINS` | `backend/main.py` | API var | Browser calls from the UI. Preview value includes the UI `workers.dev` origin and localhost. |
| `PORT` | uvicorn | Set by the API container router to `8000` | Listen port. Not a secret. |
| `AWS_ACCESS_KEY_ID` | boto3, via `lib/aws/clients.py`, and `fill_unset_secrets` | Secret on the API, Jetstream, and backfill Workers | Athena, S3, DynamoDB, SQS, and the Secrets Manager reads above. From this environment's AWS credentials. |
| `AWS_SECRET_ACCESS_KEY` | boto3 | Secret on the API, Jetstream, and backfill Workers | Same. |
| `AWS_SESSION_TOKEN` | boto3 | Secret, optional, on each of those Workers | Only for temporary credentials. Unset for the long-lived key. |
| `OPENAI_API_KEY` | `EnvVarsContainer` in `lib/load_env_vars.py` | Not forwarded. Read from Secrets Manager `openai-api-key`, key `OPENAI_API_KEY`, when the name is absent. | SQL generation on `/query`. |
| `SUPABASE_URL` | `backend/auth.py` | Not forwarded. Read from Secrets Manager `lab-data-integrations-supabase-public`, field `NEXT_PUBLIC_SUPABASE_URL`, when the name is absent. `scripts/set_api_supabase_url.py` checks the field and does not store it on the Worker. | Verifying the bearer token on `/query`. Same host as the UI. |
| `GMAIL_SENDER_EMAIL` | `backend/agentic_search/mail.py` | Not forwarded. Read from Secrets Manager `lab-data-integrations-gmail` in us-east-2, JSON field `GMAIL_SENDER_EMAIL`, when the name is absent. | Mailing `/query` results. |
| `GMAIL_APP_PASSWORD` | `backend/agentic_search/mail.py` | Not forwarded. Same secret, JSON field `GMAIL_APP_PASSWORD`, when the name is absent. | `mail.py` removes spaces before SMTP login. |
| `OTEL_EXPORTER_OTLP_HEADERS` | telemetry setup in the API, Jetstream, and the backfill app | Not forwarded. Read from Secrets Manager `lab-data-integrations-interface-grafana-cloud-oltp-header` when the name is absent. `scripts/set_grafana_otlp_header.py` uses that field for Grafana destinations and does not store it on the Worker. | Grafana. Absent means telemetry is off. |
| `MAIL_TEST_RECIPIENT` | mail smoke tests | Not forwarded. Not read by the server. | Not used by the server. |
| `DEPLOYMENT_ENVIRONMENT` | `build_resource` in the API, Jetstream, and the backfill app | Var on each of those Workers, value `cloudflare-preview` | Adds resource attribute `deployment.environment`. |
| `OTEL_RESOURCE_ATTRIBUTES` | OpenTelemetry `Resource.create` | Var on each of those Workers, value `deployment.environment=cloudflare-preview` | Same attribute, picked up by an image built before `build_resource` learned the variable. |
| `JETSTREAM_ENABLED` | `cloudflare/jetstream/src/index.ts` | Jetstream var, default `true`. A secret of the same name is rejected with error 10053. | `true` allows the supervisor to start the writer. Any other value makes the supervisor send SIGTERM. Hold the writer with `wrangler deploy --containers-rollout none --var JETSTREAM_ENABLED:false --durable-objects-code-update-mode immediate`. |
| `BACKFILL_TRIGGER_TOKEN` | `cloudflare/backfill/src/index.ts` | Backfill secret. Not copied into the container. | `POST /start` and `POST /stop`. Unset means those routes return 401 and do not start a run. |
| `NEXT_PUBLIC_API_URL` | `ui/src/lib/api.ts` | Build env, and a text binding on the UI Worker | Where the browser sends `/query`. |
| `NEXT_PUBLIC_SUPABASE_URL` | `ui/src/lib/supabase/env.ts` | Build env, and a text binding on the UI Worker. Read from Secrets Manager `lab-data-integrations-supabase-public` when unset. | Login and session. The Worker returns plain text `Internal Server Error` when this binding is missing, because `proxy.ts` throws before the page renders. |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | `ui/src/lib/supabase/env.ts` | Build env, and a text binding on the UI Worker. Same secret, JSON field of the same name. | Login and session. Same failure as the URL when the binding is missing. |
| `CLOUDFLARE_API_TOKEN` | Wrangler / `cf` | Shell only | Deploy. Not an app variable. |
| `CLOUDFLARE_ACCOUNT_ID` | Wrangler / `cf` | Shell only | Deploy. Not an app variable. |

Supabase auth on `/query` is the gate. A missing bearer token is 401
`{"detail":"Not authenticated"}`, from `HTTPBearer` in `backend/auth.py`. A
bad token is 401 `{"detail":"Invalid access token"}`.

Region, bucket, Glue database, and Athena workgroup are constants in code
(`us-east-2`). They are not env vars.

`GMAIL_SENDER_EMAIL` and `GMAIL_APP_PASSWORD` come from Secrets Manager
`lab-data-integrations-gmail` when those names are absent. The process reads
them at startup (`lib/aws/secrets_env.py`). A process that is already running
keeps the values from that start. After you rotate the secret, restart the
container.

A send check uses the sender address as the recipient. Leave
`MAIL_TEST_RECIPIENT` unset. Send one message, and do not print the address
or the app password.

## Verifying

`workers.dev` rejects the default Python user agent. The smoke script sets
one.

```bash
python scripts/cloudflare_smoke.py \
  --api-url https://ldi-api-preview.mind-technology-lab.workers.dev \
  --ui-url https://ldi-ui-preview.mind-technology-lab.workers.dev
```

The same list is the module docstring of `scripts/cloudflare_smoke.py`.
The script does not print secret values or the Access redirect URL. It checks:

1. `GET /health` returns `{"status":"ok"}`.
2. `POST /query` with no credentials returns 401 `Not authenticated`.
3. `POST /query` with `Authorization: Bearer not-a-jwt` returns 401 once
   `SUPABASE_URL` is set. That path does not touch S3.
4. `OPTIONS /query` from the UI origin echoes that origin.
5. `GET` on the UI without a service token redirects to Cloudflare Access.
   Stopping at that wall is not a check of the UI Worker.
6. With `CF-Access-Client-Id` and `CF-Access-Client-Secret` set, or with
   those fields in Secrets Manager `lab-data-integrations-access-smoke`,
   `GET /` and `GET /login` return 200 and the Supabase sign-in form
   (email, password, and "Sign in"). The script prints the elapsed
   milliseconds. A body of `Internal Server Error` fails the check.
   `cloudflare/access/apply_preview_access.py` creates the service token
   `ldi-preview-smoke` and the service auth policy on the UI app. Creating
   the token needs API token permission Access: Service Tokens Write. Without
   that permission the smoke check fails instead of treating the Access wall
   as a pass.
7. When `SUPABASE_TEST_EMAIL` and `SUPABASE_TEST_PASSWORD` are set, the
   script signs in to Supabase and `POST /query` must return 202. No test
   user is stored. Without those two variables the script says it skipped
   that check.

Jetstream, after you have confirmed the cursor is idle and the supervisor
has had a minute to start:

```bash
curl -fsS \
  -H "User-Agent: ldi-cloudflare-smoke/1.0" \
  https://ldi-jetstream-preview.mind-technology-lab.workers.dev/status
```

`running` should be `true` when `JETSTREAM_ENABLED` is `true`, and
`updated_at` on `bluesky_jetstream_cursor` should move after a flush. Do not
post `/start` on the backfill worker as a smoke check. `GET /status` on that
Worker should return `{"running": false}` until you intentionally start a run.

## Removed hosts

The API, Jetstream, and the backfill worker ran on Railway, and the UI ran
on Vercel. CloudFront was in front of the API and added an
`X-Origin-Secret` header, which `backend/origin.py` checked. The configs
in the list below are gone from the repo.

- `railway/`
- `docs/runbooks/HOW_TO_DEPLOY_BACKEND_TO_RAILWAY.md`
- `docs/runbooks/HOW_TO_DEPLOY_JETSTREAM_TO_RAILWAY.md`
- `docs/runbooks/HOW_TO_DEPLOY_BACKFILL_TO_RAILWAY.md`
- `docs/runbooks/HOW_TO_ADD_PREVIEW_BUILD_CHECKS_RAILWAY`
- `docs/runbooks/HOW_TO_DEPLOY_UI_TO_VERCEL.md`
- `backend/origin.py`

You deploy the UI, API, Jetstream, and the backfill worker only through
this runbook. Supabase auth on `/query` is the gate for that route.
Cloudflare Access is the gate for the preview hosts once Access is
enabled. See [Cloudflare Access](#cloudflare-access). `CHANGELOG.md` still
names Railway and Vercel in older entries, and the older entries were left
as written. Disconnecting the old projects is outside this repo.

`ui/package-lock.json` still lists `@vercel/og` because Next.js depends
on that package for Open Graph images. The package is not a deploy config.

`.cursor/skills/write-changelog/examples/example1.md` still says Railway.
The file is a changelog format example for another project, so the skill
stays. The Vercel-only plan example under
`create-implementation-plan/examples/` was removed.

`terraform/backend_edge/` has been removed. The destroy below was applied
in account `517478598677`. It removed `aws_cloudfront_distribution.backend`,
`aws_wafv2_web_acl.backend` (name `backend-edge`), and
`random_password.origin_secret`. The directory is gone so a later
`terraform apply` cannot create the distribution again. State remains in
the remote backend until that state is removed separately. The API Worker
secret check still needs `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
This environment did not have those names, so `ORIGIN_SECRET` was not listed
or deleted.

## Destroy the CloudFront distribution

These steps were applied before `terraform/backend_edge/` was deleted. The
lab account is
`517478598677`. The state bucket is in `us-east-2`. The WAF web ACL for
CloudFront is in `us-east-1`, because AWS requires that scope there. The
distribution itself is global. The module creates no DNS records.

Do not print `origin_secret`, `terraform output`, or a full distribution
config. The origin custom header value is the secret.

From the repo root, on the branch that still contains
`terraform/backend_edge/`:

```bash
aws sts get-caller-identity --query Account --output text
```

Stop if the account is not `517478598677`.

```bash
cd terraform/backend_edge
terraform init
```

`terraform init` reads the backend in `main.tf`. The bucket is
`lab-data-integrations-interface-tfstate` and the key is
`backend_edge/terraform.tfstate`. The region is `us-east-2`.

Read only the origin hostname. Do not print the rest of the distribution.

```bash
aws cloudfront list-distributions \
  --query "DistributionList.IsTruncated" \
  --output text
```

When the command prints `true`, the hostname may be on the next page. Set
`ORIGIN_DOMAIN` from that page and skip the first-page command below.

```bash
ORIGIN_DOMAIN=$(aws cloudfront list-distributions \
  --marker "$(aws cloudfront list-distributions --query 'DistributionList.NextMarker' --output text)" \
  --query "DistributionList.Items[?Comment=='backend API'].Origins.Items[].DomainName" \
  --output text)
printf '%s\n' "$ORIGIN_DOMAIN"
```

When the command prints `false`, one page is the full list. One page holds
100 distributions. Set `ORIGIN_DOMAIN` from that page:

```bash
ORIGIN_DOMAIN=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Comment=='backend API'].Origins.Items[].DomainName" \
  --output text)
printf '%s\n' "$ORIGIN_DOMAIN"
```

`printf` shows the hostname only. If `ORIGIN_DOMAIN` is empty after a
complete list, the distribution may already be gone. Set `ORIGIN_DOMAIN`
to the hostname you used when the module was applied, with no scheme. The
variable has no default, so destroy still needs it.

```bash
terraform plan -destroy -var origin_domain="$ORIGIN_DOMAIN"
```

Read the plan. It should destroy only `aws_cloudfront_distribution.backend`,
`aws_wafv2_web_acl.backend`, and `random_password.origin_secret`. If the
plan lists other resources, stop. If the plan shows a custom header value,
do not copy it. If the plan destroys nothing, the stack was never applied
or is already gone. Skip `terraform destroy` and go to the checks.

```bash
terraform destroy -var origin_domain="$ORIGIN_DOMAIN"
```

Terraform asks for confirmation. Answer yes only after the plan was limited
to the three resources above.

Check that the resources are gone. Empty output is the expected result.

```bash
aws cloudfront list-distributions \
  --query "DistributionList.Items[?Comment=='backend API'].Id" \
  --output text

aws wafv2 list-web-acls --scope CLOUDFRONT --region us-east-1 \
  --query "WebACLs[?Name=='backend-edge'].Name" \
  --output text

cd ../../cloudflare/backend
npx wrangler secret list
```

`wrangler secret list` prints names, not values. You need
`CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` exported, and you are in
`cloudflare/backend`, so the Worker is `ldi-api-preview`. If the list
includes `ORIGIN_SECRET`, delete that name:

```bash
npx wrangler secret delete ORIGIN_SECRET
```

If the name is absent, there is nothing to delete. Do not pass a value to
`secret delete`.

Then delete `terraform/backend_edge/` on the removal branch before merge.

## Cloudflare Access

The preview UI and API should require a one-time PIN before a person can
open them. Allowed emails end in `@northwestern.edu`, `@u.northwestern.edu`,
or `@kellogg.northwestern.edu`, plus `markptorres1@gmail.com`. The login
method on that allow policy is one-time PIN. Do not use an Include rule of
"everyone" or "any one-time PIN" without those emails. That would let any
inbox in.

This is not on the account yet. `GET /accounts/{account_id}/access/apps`
returns HTTP 403 `access.api.error.not_enabled`: Access is not enabled.
Someone has to open the Cloudflare dashboard and click Enable Access. The
token can call the Access API. The failure is the account setting, not a
missing token permission. After Access is enabled, applying the config
needs `Access: Apps and Policies Write` and `Access: Organizations,
Identity Providers, and Groups Write`. A later authentication error (code
10000) means one of those permissions is missing on the token.

The exact config is `cloudflare/access/apply_preview_access.py`. With
`CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` set:

```bash
python cloudflare/access/apply_preview_access.py
```

Until Access is enabled, that command stops and prints the same gap. It
does not print the token or the account id. It does not protect every
Worker on the account. Jetstream (`/status`) and the backfill worker stay
off this policy. Backfill `POST /start` still requires its own bearer token.

What the script creates once Access is on:

1. An identity provider named `One-time PIN login`, type `onetimepin`, if
   one does not already exist.
2. One reusable Access policy, `LDI preview OTP allow`, decision `allow`.
   Include email domains `northwestern.edu`, `u.northwestern.edu`, and
   `kellogg.northwestern.edu`, plus the email `markptorres1@gmail.com`.
   Require login method equal to that one-time PIN provider.
3. A self-hosted application `ldi-ui-preview`. Destination type `public`,
   URI `ldi-ui-preview.mind-technology-lab.workers.dev`. The allow policy
   is the only policy. Session duration `24h`. The login page redirects
   to the one-time PIN provider.
4. A self-hosted application `ldi-api-preview` for
   `ldi-api-preview.mind-technology-lab.workers.dev`, with the same allow
   policy. The destination has public overrides for `/health` and `/query`.
   An override makes that path skip Access. Override paths do not cover
   subpaths, which matches the two routes the API actually serves.

`/query` stays reachable without an Access login because the UI calls it
from the browser (`ui/src/lib/api.ts`). The UI host and the API host are
different sites: `workers.dev` is a public suffix, so the Access cookie
from the UI is not sent to the API. A service token would have to be
inlined into the client bundle to go with that `fetch`, and that would
publish the token. The public override is the fit. Supabase still rejects
a missing or bad bearer token. `/health` stays public so a smoke check
can call it without a PIN. Any other path on the API host, such as the
generated docs, still asks for the PIN.

Dashboard equivalent, if you apply it by hand:

1. Zero Trust, then Integrations, then Identity providers. Add One-time PIN.
2. Access controls, then Policies. Create a reusable Allow policy with the
   emails and domains above, and require One-time PIN.
3. Add a self-hosted application for the UI hostname and attach that policy.
4. Add a self-hosted application for the API hostname, attach that policy,
   and add destination overrides that make `/health` and `/query` public.
5. Do not add an `all_workers` destination.

## Open questions

None from the image split. On 2026-10-23 the preview Workers were rolled
onto these images. `docker images` reports the API image at 1.31 GB,
Jetstream at 1.16 GB, and the backfill image at 908 MB. The previous
shared image was 3.77 GB.
