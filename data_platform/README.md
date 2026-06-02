# Data platform

Batch pipeline per platform:

```text
ingestion → preprocessing → generate_features → curate
```

Each logical collection is identified by **`dataset_id`** (`{platform}_<uuid>`), pinned in ingestion YAML (e.g. `mirrorview.yaml`) and recorded under `data_platform/data/{platform}/{dataset_id}/`. Downstream CLIs require `--dataset-id`; curate YAML is filter-only.

## Stages

| Platform | Stage | Module | Output |
|----------|-------|--------|--------|
| bluesky | Ingestion | `data_platform/ingestion/` | `data/bluesky/{dataset_id}/raw/{timestamp}/` |
| bluesky | Preprocessing | `data_platform/preprocessing/` | `.../preprocessed/{timestamp}/posts.csv` |
| bluesky | Features | `data_platform/generate_features/` | `.../features/{feature}.csv`, `metadata.json` |
| bluesky | Curate | `data_platform/curate/` | `.../curated/{timestamp}/` |
| twitter | Ingestion | `data_platform/ingestion/` | `data/twitter/{dataset_id}/raw/{timestamp}/posts.csv` |
| twitter | Preprocessing | `data_platform/preprocessing/` | `.../preprocessed/{timestamp}/posts.csv` |
| twitter | Features | `data_platform/generate_features/` | `.../features/{feature}.csv`, `metadata.json` |
| twitter | Curate | `data_platform/curate/` | `.../curated/{timestamp}/mirrorview.csv` |

## Commands

Ingestion reads `dataset_id` from the ingestion config:

```bash
PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py --config mirrorview.yaml
```

Large scale syncs checkpoint per keyword in `raw/{timestamp}/metadata.json` and append to `posts.csv` after each keyword completes. Resume after interrupt or rate limits:

```bash
PYTHONPATH=. uv run python data_platform/ingestion/sync_bluesky.py --config mirrorview_scale.yaml --resume
```

Inspect unfinished keywords:

```bash
jq '.keywords | to_entries | map(select(.value.status != "completed")) | length' \
  data_platform/data/bluesky/<dataset_id>/raw/<timestamp>/metadata.json
```

See [docs/plans/2026-05-30_sync_bluesky_resumable_482910/README.md](../docs/plans/2026-05-30_sync_bluesky_resumable_482910/README.md).

Preprocess, features, and curate require the same `--dataset-id` as in ingestion YAML:

```bash
PYTHONPATH=. uv run python data_platform/preprocessing/preprocess_bluesky.py \
  --dataset-id bluesky_f47ac10b-58cc-4372-a567-0e02b2c3d479

PYTHONPATH=. uv run python data_platform/generate_features/generate_bluesky_features.py \
  --dataset-id bluesky_f47ac10b-58cc-4372-a567-0e02b2c3d479 \
  --batch-size 64

PYTHONPATH=. uv run python data_platform/curate/curate_bluesky.py \
  --dataset-id bluesky_f47ac10b-58cc-4372-a567-0e02b2c3d479 \
  --config mirrorview.yaml
```

### Twitter (preprocess, features, curate)

Example `dataset_id`: `twitter_f47ac10b-58cc-4372-a567-0e02b2c3d479` (from ingestion YAML).

```bash
PYTHONPATH=. uv run python data_platform/preprocessing/preprocess_twitter.py \
  --dataset-id twitter_f47ac10b-58cc-4372-a567-0e02b2c3d479

PYTHONPATH=. uv run python data_platform/generate_features/generate_twitter_features.py \
  --dataset-id twitter_f47ac10b-58cc-4372-a567-0e02b2c3d479 \
  --batch-size 64

PYTHONPATH=. uv run python data_platform/curate/curate_twitter.py \
  --dataset-id twitter_f47ac10b-58cc-4372-a567-0e02b2c3d479 \
  --config mirrorview.yaml
```

Mirrorview config: `data_platform/curate/configs/twitter/mirrorview.yaml` (same filter chain as Bluesky/Reddit).

See [docs/plans/2026-06-01_twitter_preprocess_features_curate_482913/plan.md](../docs/plans/2026-06-01_twitter_preprocess_features_curate_482913/plan.md).

### Reddit (preprocess, features)

Example `dataset_id`: `reddit_f47ac10b-58cc-4372-a567-0e02b2c3d479` (from ingestion YAML).

```bash
PYTHONPATH=. uv run python data_platform/preprocessing/preprocess_reddit.py \
  --dataset-id reddit_f47ac10b-58cc-4372-a567-0e02b2c3d479

PYTHONPATH=. uv run python data_platform/generate_features/generate_reddit_features.py \
  --dataset-id reddit_f47ac10b-58cc-4372-a567-0e02b2c3d479 \
  --batch-size 64
```

One-time migration from the legacy flat layout:

```bash
PYTHONPATH=. uv run python scripts/migrate_bluesky_dataset_id.py --dry-run
PYTHONPATH=. uv run python scripts/migrate_bluesky_dataset_id.py
```

## Curate (join + business rules)

Joins the latest preprocessed posts with all feature label CSVs (DuckDB), then applies YAML filters.

Mirrorview config: `data_platform/curate/configs/bluesky/mirrorview.yaml`

- Filters: `news_or_opinion_category == opinion`, `is_political`, `political_stance in [left, right]`, `is_self_contained`, `is_structurally_complete` all true.
- `is_news_or_opinion.category` is exposed as **`news_or_opinion_category`** in the wide table and export CSV.
