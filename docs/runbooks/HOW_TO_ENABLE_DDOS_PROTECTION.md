# How to Enable DDoS Protection

## Overview

The API, UI, Jetstream, and backfill worker are Cloudflare Workers and Containers. Cloudflare filters traffic to those hosts. There is no separate CloudFront distribution, and the API does not check a shared-secret header.

Application checks stay in the app:

- `/query` requires a Supabase bearer token (`backend/auth.py`).
- The preview UI and API hosts should sit behind Cloudflare Access. See [HOW_TO_DEPLOY_TO_CLOUDFLARE.md](HOW_TO_DEPLOY_TO_CLOUDFLARE.md).
- Backfill `POST /start` and `POST /stop` require `BACKFILL_TRIGGER_TOKEN`.

The CloudFront injector and the API middleware that checked `X-Origin-Secret` are removed. See [Removed hosts](HOW_TO_DEPLOY_TO_CLOUDFLARE.md#removed-hosts).
