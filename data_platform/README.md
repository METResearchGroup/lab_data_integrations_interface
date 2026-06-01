# Data platform

Batch pipeline for Bluesky data:

```text
ingestion → preprocessing → generate_features → curate
```

Each logical collection is identified by **`dataset_id`** (`bluesky_<uuid>`), pinned in ingestion YAML (e.g. `mirrorview.yaml`) and recorded in `data/bluesky/{dataset_id}/dataset.json`. Downstream CLIs require `--dataset-id`; curate YAML is filter-only.

## Stages

| Stage | Module | Output |
|-------|--------|--------|
| Ingestion | `data_platform/ingestion/` | `data/bluesky/{dataset_id}/raw/{timestamp}/` |
| Preprocessing | `data_platform/preprocessing/` | `data/bluesky/{dataset_id}/preprocessed/{timestamp}/posts.csv` |
| Features | `data_platform/generate_features/` | `data/bluesky/{dataset_id}/features/{feature}.csv`, `metadata.json` |
| Curate | `data_platform/curate/` | `data/bluesky/{dataset_id}/curated/{timestamp}/` |

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
  --batch-size 64 --no-opik

PYTHONPATH=. uv run python data_platform/curate/curate_bluesky.py \
  --dataset-id bluesky_f47ac10b-58cc-4372-a567-0e02b2c3d479 \
  --config mirrorview.yaml
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
