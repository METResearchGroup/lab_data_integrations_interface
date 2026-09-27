# Reddit Pushshift dump labeling

Label high-toxicity Reddit comments from two Pushshift parquet batches (`RC_2025-05`, `RC_2025-06`) using prod feature generation and curation code. Perspective scores already exist in `prob_toxic`; this pipeline seeds `is_toxic_tiered` from those scores and runs the six LLM classifiers only. All artifacts stay under this experiment folder via runtime `DATA_ROOT` patching—no changes to `data_platform/`.

## Prerequisites

- Run from repo root with `PYTHONPATH=.`
- LLM env vars required for feature generation (same as prod, e.g. `OPENAI_API_KEY`)
- Source parquets: `RC_2025-05/high_toxic_comments.parquet` (28,457 rows), `RC_2025-06/high_toxic_comments.parquet` (33,635 rows)

## Batch config

See [`batches.yaml`](batches.yaml) for frozen dataset IDs and parquet paths.

## Run order

### Pilot (10 rows, RC_2025-05)

```bash
PYTHONPATH=. uv run python experiments/reddit_data_dump_labeling_2026_06_16/prepare_batch.py --batch RC_2025-05 --limit 10
PYTHONPATH=. uv run python experiments/reddit_data_dump_labeling_2026_06_16/seed_toxicity_features.py --batch RC_2025-05 --limit 10
for f in is_news_or_opinion is_political is_likely_spam is_self_contained is_structurally_complete political_stance; do
  PYTHONPATH=. uv run python experiments/reddit_data_dump_labeling_2026_06_16/run_features.py --batch RC_2025-05 --limit 10 --features $f --batch-size 4 --max-concurrency 4
done
PYTHONPATH=. uv run python experiments/reddit_data_dump_labeling_2026_06_16/run_curate.py --batch RC_2025-05
```

### Full batch (one batch at a time)

```bash
PYTHONPATH=. uv run python experiments/reddit_data_dump_labeling_2026_06_16/prepare_batch.py --batch RC_2025-05
PYTHONPATH=. uv run python experiments/reddit_data_dump_labeling_2026_06_16/seed_toxicity_features.py --batch RC_2025-05
for f in is_news_or_opinion is_political is_likely_spam is_self_contained is_structurally_complete political_stance; do
  PYTHONPATH=. uv run python experiments/reddit_data_dump_labeling_2026_06_16/run_features.py --batch RC_2025-05 --features $f
done
PYTHONPATH=. uv run python experiments/reddit_data_dump_labeling_2026_06_16/run_curate.py --batch RC_2025-05
```

Repeat for `RC_2025-06`.

## Output layout

```
experiments/reddit_data_dump_labeling_2026_06_16/data/reddit/{dataset_id}/
  dataset.json
  preprocessed/{run}/comments.csv
  features/is_toxic_tiered.csv
  features/{feature}.csv
  features/metadata.json
  curated/{run}/mirrorview.csv
  curated/{run}/metadata.json
```

## Tests

```bash
uv run pytest tests/experiments/reddit_pushshift_labeling/ -q
```

## Notes

- `is_toxic_tiered` is seeded from `prob_toxic`; the Perspective API is not called.
- LLM features excluded from seeding: run via `run_features.py` only.
- Generated data under `data/` is gitignored.
