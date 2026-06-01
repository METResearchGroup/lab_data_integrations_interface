# Resumable Bluesky sync

Plan for checkpointed ingestion: keyword ledger in `metadata.json`, append-per-keyword `posts.csv`, tenacity retries on search_posts, and `--resume`.

## Resume

```bash
export DATASET_ID=bluesky_c4e8a2f1-7b3d-4e6a-9c12-8f5d3a2b1e70
PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py --config mirrorview_scale.yaml --resume
```

## Inspect unfinished keywords

```bash
jq -r '.keywords | to_entries[] | select(.value.status != "completed") | "\(.key): \(.value.status)"' \
  data_platform/data/bluesky/$DATASET_ID/raw/<timestamp>/metadata.json | head
```

Pending count:

```bash
jq '.keywords | to_entries | map(select(.value.status != "completed")) | length' \
  data_platform/data/bluesky/$DATASET_ID/raw/<timestamp>/metadata.json
```

## Keyword statuses

`pending` → `in_progress` → `completed` | `failed` | `skipped`

- CSV rows are appended only after all pages for a keyword succeed.
- `in_progress` or `failed` on resume: keyword is re-fetched from page 1 (no cursor checkpoint).
