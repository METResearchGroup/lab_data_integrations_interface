# Perspective API labeling of posts

We now have a data injection pipeline that gives us every single post in Bluesky. We can get this looking forward into the future, but we aren't able to get this yet on past data. That's okay. Right now, we want a proof of concept of how useful this data is, so now what we can do is take all the posts that we do have and run the prospective API classifier on those posts.

Approach:

1. Get Bluesky raw posts, in chunks of ~1M posts.
2. For each post, run the Perspective API classifier.
3. Store locally as labels/{date}.parquet

The model for the Perspective API is defined in `feature_generation/perspective_api/schemas.py`, and the model code is in `feature_generation/perspective_api/model.py`.

Our current posts Athena table prunes to a given day partition (e.g., `WHERE created_at_day = ...`), which makes queries more efficient.

We'll fetch just posts that were created 2026-08-09 and 2026-08-10.

## Post counts (2026-08-09 and 2026-08-10)

Queried via `get_post_count_by_day.py` against `bluesky_raw.posts`:

```markdown
database: bluesky_raw
workgroup: bluesky_raw_maintenance

created_at_day	post_count
2026-08-09	3124215
2026-08-10	3463641

total: 6587856
```

Run from repo root:

```bash
PYTHONPATH=. uv run python experiments/perspective_api_labeling_2026_08_11/get_post_count_by_day.py
```

## Labeling

1. Download posts (one Parquet per day under `data/`):

```bash
PYTHONPATH=. uv run python experiments/perspective_api_labeling_2026_08_11/download_posts_by_day.py
```

2. Label with Perspective API. Progress is flushed every 10k rows to
   `labels/tmp/{date}/{hash}.parquet`. Re-runs skip URIs already present in that tmp dir.

```bash
PYTHONPATH=. uv run python experiments/perspective_api_labeling_2026_08_11/label_posts.py \
  experiments/perspective_api_labeling_2026_08_11/data/2026-08-09.parquet

# Optional: smoke-test a small slice
PYTHONPATH=. uv run python experiments/perspective_api_labeling_2026_08_11/label_posts.py \
  experiments/perspective_api_labeling_2026_08_11/data/2026-08-09.parquet --limit 1000
```

Use `--batch-size 20 --delay-seconds 0.25` for stable throughput (~60-70 QPS). Larger batches (e.g. 90) produce frequent 503s and slow retries. A full day (~3M posts) takes on the order of many hours. Use `--limit` for a smoke test first.

3. Consolidate tmp chunks into a single day file and clear the tmp dir:

```bash
PYTHONPATH=. uv run python experiments/perspective_api_labeling_2026_08_11/consolidate_labels.py \
  --date 2026-08-09
```

Output layout:

```
data/{date}.parquet
labels/tmp/{date}/{hash}.parquet   # mid-run flushes
labels/{date}.parquet              # consolidated
```
