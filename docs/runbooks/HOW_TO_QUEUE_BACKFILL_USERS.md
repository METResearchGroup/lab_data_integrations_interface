# How to Queue Users for Backfill

## Overview

Backfill workers (`fetch_repos`) only fetch DIDs that are on the
`bluesky-backfill-dids` SQS queue. Getting users there is two local commands:

1. **Discover**: page the relay's `listRepos` and record DIDs in DynamoDB as
   `discovered`. Resumes from a stored cursor, so reruns continue where the
   last one stopped.
2. **Enqueue**: send every `discovered` DID to SQS and mark it `queued`.

Needs AWS credentials for `us-east-2` (DynamoDB, SQS). Run from the repo root.

## Commands

```bash
# --count is how many new DIDs to add this run.
PYTHONPATH=. uv run python -m bluesky_backfill_app.gather_users.discovery.main --count 1000

PYTHONPATH=. uv run python -m bluesky_backfill_app.gather_users.enqueue.main
```

The enqueue exits once nothing `discovered` is left. To queue more users later,
rerun both commands. A discovery run that fails partway has already added some
DIDs, so rerunning the same `--count` adds that many again on top.
