# Data platform

Batch pipeline for Bluesky data:

```text
ingestion → preprocessing → generate_features → curate
```

## Stages

| Stage | Module | Output |
|-------|--------|--------|
| Ingestion | `data_platform/ingestion/` | `data/bluesky/raw/{timestamp}/` |
| Preprocessing | `data_platform/preprocessing/` | `data/bluesky/preprocessed/{timestamp}/posts.csv` |
| Features | `data_platform/generate_features/` | `data/bluesky/features/{timestamp}/*.csv` |
| Curate | `data_platform/curate/` | `data/bluesky/curated/{timestamp}/` |

## Curate (join + business rules)

Joins the latest preprocessed posts with all feature label CSVs (DuckDB), then applies YAML filters.

```bash
PYTHONPATH=. uv run python data_platform/curate/curate_bluesky.py --config mirrorview.yaml
```

Mirrorview config: `data_platform/curate/configs/bluesky/mirrorview.yaml`

- Filters: `news_or_opinion_category == news`, `is_political`, `is_self_contained`, `is_structurally_complete` all true.
- `is_news_or_opinion.category` is exposed as **`news_or_opinion_category`** in the wide table and export CSV.
