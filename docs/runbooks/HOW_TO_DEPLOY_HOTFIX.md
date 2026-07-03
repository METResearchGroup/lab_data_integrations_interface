---
name: deploy-hotfix
description: >-
  Deploy an urgent production fix. Use when shipping a hotfix PR, verifying it
  on preview (Vercel or Railway), promoting to production, and confirming
  services and telemetry are healthy after deploy.
---

# How to Deploy a Hotfix

Ship a small, urgent fix to production with preview verification and post-deploy checks.

## Steps

1. **Open a PR** with the minimal change that fixes the issue.
2. **Tag the PR** with the `hotfix` label.
3. **Verify on preview** that the patch actually fixes the issue:
   - Local dev, and/or
   - Vercel preview (UI), and/or
   - Railway preview (backend)
4. **Deploy to production** (merge and promote as usual for the affected service).
5. **Confirm services are up**:
   - UI (Vercel)
   - Backend (Railway)
   - Any other services touched by the change
6. **Check telemetry** for stability and regressions:
   - Errors / logs for the affected paths
   - Core metrics you care about for this change

## Done when

- Preview showed the fix working
- Production deploy completed
- Services are healthy
- Telemetry looks stable (no new error spike, no drop in core metrics)
