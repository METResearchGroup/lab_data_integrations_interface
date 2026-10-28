# DevOps additions

[Overview](plan.md). Do these in order. Each item says what already exists, what still depends on draft [PR #245](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/245) or [PR #247](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/247), and why it is on the list. Size labels are the source notes' labels: small is a short change, medium is a larger one.

Railway stays the production path until the Cloudflare cutover is done. #245 is a preview draft, and the Railway runbooks on `main` are still how you deploy the backend, Jetstream, and backfill.

## 1. Deploy workflow with an authenticated smoke

GitHub Actions should run `wrangler deploy` and then `scripts/cloudflare_smoke.py`, with a dedicated Supabase test user and an Access service token. A failed smoke fails the deploy.

`scripts/cloudflare_smoke.py` exists only on #245. CI on `main` and on that branch does not call it. The script already covers `/health`, the Access redirect, the UI behind the service token, and `POST /query` when `SUPABASE_TEST_EMAIL` and `SUPABASE_TEST_PASSWORD` are set. The signed-in `/query` check is the one that sees a rejected JWT. The UI check is the one that sees a 500 after Access. A check that stops at the Access redirect cannot see either failure. The authenticated UI check fails closed when the Access token is missing, which is the behavior you want in a deploy job.

The service token name on the draft is `ldi-preview-smoke`, created by `cloudflare/access/apply_preview_access.py`. The token fields can live in Secrets Manager `lab-data-integrations-access-smoke`. The workflow must read those names from GitHub Actions secrets or from the job's environment. It must not print the values.

Size in the source notes: medium.

Depends on #245, because the smoke script and the wrangler projects are not on `main`. #247 does not change the smoke script. #247 is stacked on #245, so the slimmer API image, which includes `cryptography`, is included only when that stack merges together. The #245 image without `cryptography` is the ES256 failure.

## 2. Pre-deploy config check

Fail the deploy when a required Worker binding or secret is missing, or when the value has the wrong shape. The example from the notes is a Supabase URL whose host is not a `supabase.co` host. Log names and hashes only. Do not log values.

The preview failures were a missing pair of UI text bindings (`NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`) and a Secrets Manager URL whose host was a CloudFront host. The host should have been the Supabase project host. `scripts/set_api_supabase_url.py` on #245 copies `NEXT_PUBLIC_SUPABASE_URL` from Secrets Manager `lab-data-integrations-supabase-public` onto the API Worker secret `SUPABASE_URL`. The copy script does not check the host shape. The check belongs next to that copy, before `wrangler deploy`.

Size in the source notes: small.

Depends on #245 for the Worker secret names. The host shape rule can be written before the cutover, and it should run against Railway and Secrets Manager too, because the bad URL was in Secrets Manager.

## 3. Container startup and memory smoke

After deploy, each container should become healthy within a bounded number of minutes, and stay under its memory ceiling for 5 minutes. One backfill run should process 10 known-small accounts.

#245 starts Jetstream with `ctx.container.start()` and a minute cron, and it does not probe a port. The backfill worker starts only on `POST /start` with `BACKFILL_TRIGGER_TOKEN`. Nothing in CI starts a backfill. On `main` the flush cap is 2 GiB. On #245 it is 128 MiB after the 4 GiB preview ran out of memory. A memory smoke is what would catch the cap regressing upward again. The notes did not pick the minute bound. Leave the minute bound as an explicit input when you write the job, and record the number in the runbook.

Size in the source notes: medium.

Depends on #245 for the container Workers. The 10-account backfill also needs a list of account DIDs that you are willing to rerun. The repo does not contain that list.

## 4. One rollback command, plus a runbook

You should be able to roll back with one command, either `wrangler rollback` or a redeploy of the previous version, and the steps should live in a runbook next to [`docs/runbooks/HOW_TO_DEPLOY_HOTFIX.md`](../../runbooks/HOW_TO_DEPLOY_HOTFIX.md). Keep the Railway deploy path until cutover. [`docs/runbooks/HOW_TO_DEPLOY_HOTFIX.md`](../../runbooks/HOW_TO_DEPLOY_HOTFIX.md) is the current hotfix doc and it is about the existing hosts, not Cloudflare.

Whether `wrangler rollback` includes the container image is unverified. See the [overview](plan.md#not-verified). Until that is known, the runbook should say which artifact the command restores, and the fallback should be a redeploy of a known image tag.

Size in the source notes: small.

The command itself does not depend on #247. Using it against the preview does depend on #245, because there is no Cloudflare Worker on `main`.

## 5. Separate preview and production wrangler environments

Preview and production should be separate wrangler environments, with separate secrets. A pull request deploys preview. Production is a manual workflow with a GitHub Environment approval.

#245 is one preview config per Worker. The names end in `-preview`, and `workers_dev` is true. There is no `env.production` block. Do not point production secrets at those preview Worker names.

Size in the source notes: medium.

Depends on #245 as the preview you would split. Production should not be created by merging the draft as-is.

## 6. Cost guardrails

Add four limits.

- An Athena workgroup per-query scan limit. AWS documents the control at [setting workgroup query limits](https://docs.aws.amazon.com/athena/latest/ug/workgroups-setting-control-limits-cloudwatch.html). `terraform/data_platform/main.tf` defines `lab-data-integrations-interface` and `lab-data-integrations-interface-olap` with result locations only. `terraform/bluesky_ingestion_jetstream/maintenance.tf` publishes CloudWatch metrics for the maintenance workgroup and does not set a scan cutoff.
- AWS Budgets at 50, 80, and 100 percent. AWS documents the budgets at [managing costs with budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html). The repo has no budget resource.
- A monthly limit on the OpenAI project used for `/query`.
- Cloudflare billing notifications.

The source notes give the reason as a 10x data-cost jump on 2026-10-14, and a backfill enqueue of $50 to $100. Those amounts are not in the repo. The guardrails are still worth adding, because Athena and OpenAI spend are unbounded in the current Terraform.

Size in the source notes: small.

The Athena and AWS budget changes are on `main`'s Terraform and do not depend on #245. Cloudflare billing notifications do.

## 7. Cloudflare in Terraform

Move Access applications and policies, rate limit rules, and notification destinations into Terraform. Today, preview Access is `cloudflare/access/apply_preview_access.py` on #245. The script is imperative, it is not on `main`, and it does not cover Jetstream or backfill. Rate limit rules are not in that script. `terraform/backend_edge/` is AWS WAF and CloudFront, from merged [PR #242](https://github.com/METResearchGroup/lab_data_integrations_interface/pull/242), and it is a different edge than Cloudflare.

Size in the source notes: medium.

Depends on #245, because there is no Cloudflare Access config on `main` to import. Keep the Python script until the Terraform matches what the script created, and then stop running both.

## 8. Retire the CloudFront path and the Railway config after cutover

After the Cloudflare production environment is the one users hit, remove `terraform/backend_edge/` and the Railway config, and close [issue #192](https://github.com/METResearchGroup/lab_data_integrations_interface/issues/192). The #245 deploy runbook already says both `terraform/backend_edge/` and `backend/origin.py` stay until Railway and CloudFront are retired. Do not remove them in the same change that adds the preview.

Size in the source notes: small.

Depends on the production cutover, which depends on #245 and on item 5. #192 is not moot yet.

## What the first deploy items would have caught

The six failures in the [overview](plan.md#recent-failures-the-plan-is-answering) split across the items above.

| Failure | Which item catches a repeat |
| --- | --- |
| UI 500 from missing Supabase bindings | Item 2, and item 1 once the UI check runs behind Access |
| Supabase URL host was CloudFront | Item 2, if the check rejects a host that is not `supabase.co` |
| Real session rejected because ES256 support was missing | Item 1, the signed-in `/query` check |
| Jetstream OOM from the 2 GiB flush cap | Item 3, the memory smoke. Item 1 does not watch RSS |
| Port probe aborting the Durable Object | Item 3, the startup smoke. A `/health` check on the API does not start Jetstream |
| Backfill never run | Item 3, the 10-account run |

The source notes said the deploy workflow, the config check, smoke, and rollback would have caught 3 of the 6. That matches the first three rows. Rollback is how you leave the bad deploy, not how you detect it.
