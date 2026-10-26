---
name: deploy-hotfix
description: >-
  Deploy an urgent fix. Use when shipping a hotfix PR, verifying it on the
  Cloudflare preview, and confirming services and telemetry are healthy
  after deploy.
---

# How to Deploy a Hotfix

Ship a small, urgent fix with preview verification and post-deploy checks.

## Steps

1. **Open a PR** with the minimal change that fixes the issue.
2. **Tag the PR** with the `hotfix` label.
3. **Verify on preview** that the patch actually fixes the issue:
   - Local dev, and/or
   - the Cloudflare preview Workers. See [HOW_TO_DEPLOY_TO_CLOUDFLARE.md](HOW_TO_DEPLOY_TO_CLOUDFLARE.md).
4. **Ship the fix** by merging. The live path in this repo is the Cloudflare preview in [HOW_TO_DEPLOY_TO_CLOUDFLARE.md](HOW_TO_DEPLOY_TO_CLOUDFLARE.md).
5. **Confirm the UI Worker and the API Container answer.** Also confirm Jetstream or the backfill worker when the change touches them.
6. **Check telemetry** for stability and regressions:
   - Errors / logs for the affected paths
   - Core metrics you care about for this change

## Done when

- Preview showed the fix working
- The fix is merged
- Services are healthy
- Telemetry looks stable (no new error spike, no drop in core metrics)
