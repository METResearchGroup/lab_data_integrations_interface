# How to Deploy to Cloudflare

## Overview

The FastAPI backend runs as a Cloudflare Container. The Next.js UI in `ui/`
runs as a Cloudflare Worker, built with vinext. Jetstream runs as its own
always-on Container. The backfill fetch worker runs as its own Container that
you start when you want a run. Object storage stays on AWS S3. This deploy
does not use Cloudflare R2.

Railway config stays in the repo. See [What can be removed later](#what-can-be-removed-later).

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
well under a dollar at these rates. A run you forget is stopped 6 hours
after the latest `/start`, so one forgotten run is a few dollars, not a
month of `standard-1`.

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
Jetstream container running. This environment has no Railway token, so the
Railway API cannot answer the question. The cursor is the record that a
writer committed.

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

Set the token from `cloudflare/backfill/`, with the Cloudflare credentials
exported. Pick the token yourself and store it where you can read it again.
Wrangler will not show it back to you.

```bash
cd cloudflare/backfill
printf '%s' "$BACKFILL_TRIGGER_TOKEN" | npx wrangler secret put BACKFILL_TRIGGER_TOKEN
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

Check whether a run is up, without starting one:

```bash
curl -fsS \
  -H "User-Agent: ldi-backfill-trigger/1.0" \
  https://ldi-backfill-preview.mind-technology-lab.workers.dev/status
```

The first `/start` can take several minutes while Cloudflare pulls the image.
If the client gives up, check `/status` before you post `/start` again.

A run stops 6 hours after the latest `POST /start`. Three clocks enforce that.

`/start` calls `setInactivityTimeout` for 6 hours. Without that call,
Cloudflare stops the container shortly after the Durable Object goes idle.
The process then ends when the `/start` request finishes. The constructor
sets the remaining time again if the object restarts while the process is
still up.

`sleepAfter` is `6h`, so the default activity hook sends SIGTERM at 6 hours
on a Durable Object that stays in memory. `/start` also stores a schedule
that calls `stop()` 6 hours later. That schedule still fires if the Durable
Object restarts and refreshes its in-memory timer. The SQS loop does not
extend the platform timeout, the library timer, or the stored deadline.
Another `POST /start` while the process is already up moves the deadline out
by 6 hours from that request. There is no cron, so a process that exits
stays down until you post `/start` again.

SIGTERM is what `/stop` sends, and it is what the 6 hour deadline sends.
`bluesky_backfill_app/fetch_repos/main.py` turns SIGTERM into
`KeyboardInterrupt`. The `run()` finally block flushes a remaining buffer
with reason `stop`, and then telemetry is flushed. Cloudflare waits about 15
minutes after SIGTERM before SIGKILL, which covers that drain. The Railway
service used a 300 second drain.

Deploy the Worker from `cloudflare/backfill/` the same way as Jetstream,
with an AWS secrets file, and without calling `/start`. Put
`BACKFILL_TRIGGER_TOKEN` only when you are about to run a backfill.

