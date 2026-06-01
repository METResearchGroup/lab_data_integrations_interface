# Dataset ID provenance (plan assets)

Implementation plan: Cursor plan `dataset_id_provenance_16a4b859`.

## Overview

`dataset_id` (`bluesky_<uuid>`) is the provenance boundary for Bluesky batch data. Storage layout: `data/bluesky/{dataset_id}/{stage}/{timestamp}/`. Ingestion YAML owns the ID; downstream CLIs take `--dataset-id`.

## Verification

- `PYTHONPATH=. uv run pytest tests/data_platform/ -q`
- `PYTHONPATH=. uv run python scripts/migrate_bluesky_dataset_id.py --dry-run`
- `PYTHONPATH=. uv run python data_platform/curate/curate_bluesky.py --dataset-id <id> --config mirrorview.yaml`
