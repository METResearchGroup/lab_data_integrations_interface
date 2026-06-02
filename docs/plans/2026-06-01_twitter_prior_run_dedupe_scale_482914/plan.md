# Twitter Prior-Run Dedupe + 10k Scale Plan

Saved from implementation plan `twitter_dedupe_scale_sync_8a3c22d6`. Contract frozen 2026-06-01.

## Remember
- Exact file paths always
- Exact commands with expected output
- DRY, YAGNI, TDD, frequent commits
- Maximum safely delegable parallelism
- Delegated tasks must be impossible to misread

## Plan assets
- `docs/plans/2026-06-01_twitter_prior_run_dedupe_scale_482914/`
- This file: `docs/plans/2026-06-01_twitter_prior_run_dedupe_scale_482914/plan.md`

## Overview
Implement Reddit-parity deduplication for Twitter ingestion so new raw runs can skip tweet IDs captured in prior raw runs of the same dataset, then add a dedicated `mirrorview_scale.yaml` config that targets 10,000 rows and runs cleanly through preprocessing, feature generation, and curation.

## Happy Flow
1. Ingestion reads `fetch.dedupe_tweets_from_prior_raw_runs` from [`data_platform/ingestion/configs/twitter/mirrorview_scale.yaml`](data_platform/ingestion/configs/twitter/mirrorview_scale.yaml), then [`sync_twitter.py`](data_platform/ingestion/sync_twitter.py) preloads prior-run tweet IDs and filters fetched rows before append.
2. `sync_twitter.py` writes only unseen tweet IDs to `raw/<timestamp>/posts.csv` and updates metadata counters (`row_count`, per-keyword stats, duplicate-skip counter).
3. Preprocessing via [`data_platform/preprocessing/preprocess_twitter.py`](data_platform/preprocessing/preprocess_twitter.py) reads latest raw run and writes filtered `preprocessed/<timestamp>/posts.csv`.
4. Feature generation via [`data_platform/generate_features/generate_twitter_features.py`](data_platform/generate_features/generate_twitter_features.py) labels latest preprocessed posts into six feature CSVs under `features/`.
5. Curation via [`data_platform/curate/curate_twitter.py`](data_platform/curate/curate_twitter.py) joins preprocessed + feature CSVs and exports `curated/<timestamp>/mirrorview.csv`.

## Interface or Contract Freeze
- **New ingestion config flag (Twitter only):** `fetch.dedupe_tweets_from_prior_raw_runs: bool` (default false when missing).
- **No schema changes** to `SyncTwitterPostModel` or `posts.csv` columns.
- **Deduplication key stays:** `tweet_id`.
- **Behavioral contract:**
  - Always dedupe within current run (existing behavior).
  - If flag true, additionally dedupe against all prior raw runs for same dataset ID.
- **No changes** to preprocess/features/curate contracts.
- **Scale dataset ID (frozen):** `twitter_a8f3c22d-6b14-4e9a-9d2f-1c7e5a9b3d48`
- **Metadata counter:** `tweets_skipped_as_duplicates` (int, cumulative per run)

## Before/After (files/functions)
- [`data_platform/ingestion/sync_twitter.py`](data_platform/ingestion/sync_twitter.py)
  - **Before:** `_sync_one_keyword(...)` filters against `storage.load_seen_tweet_ids(output_dir, ...)` only.
  - **After:** `_sync_one_keyword(...)` filters against `current_run_seen_ids ∪ prior_run_seen_ids` when dedupe flag enabled.
  - **Before:** `run_keyword_sync_loop(...)` has no prior-run preload or duplicate-skip metadata counter.
  - **After:** `run_keyword_sync_loop(...)` optionally loads prior IDs once and threads them through sync calls; tracks `tweets_skipped_as_duplicates` metadata.
- [`data_platform/ingestion/configs/twitter/mirrorview_scale.yaml`](data_platform/ingestion/configs/twitter/mirrorview_scale.yaml)
  - **Before:** file does not exist.
  - **After:** new scale config with `max_rows: 10000`, `limit_per_keyword: 200`, same keywords as `mirrorview.yaml`, and `dedupe_tweets_from_prior_raw_runs: true`.
- [`tests/data_platform/ingestion/test_sync_twitter_checkpoint.py`](tests/data_platform/ingestion/test_sync_twitter_checkpoint.py)
  - **Before:** file does not exist.
  - **After:** new ingestion checkpoint tests covering prior-run dedupe parity and resume behavior.

## Serial Coordination Spine
1. Create config + code contract freeze (flag name, default behavior, metadata key names). **Done**
2. Implement Twitter ingestion dedupe logic in `sync_twitter.py`.
3. Add Twitter ingestion checkpoint tests for new behavior.
4. Add `mirrorview_scale.yaml` and run validation commands.
5. Execute pipeline runbook commands and collect outputs/paths.

## Parallel Task Packets

### TW-D1 — Ingestion dedupe parity implementation
- **Objective:** Add optional prior-run dedupe to Twitter ingestion with minimal localized changes.
- **Files allowed to change:** `data_platform/ingestion/sync_twitter.py`
- **Implementation steps:**
  1. Add optional preload in `run_keyword_sync_loop(...)`.
  2. Thread `prior_tweet_ids` into `_sync_one_keyword(...)`.
  3. In `_sync_one_keyword(...)`, compute `seen_ids` as union of prior IDs + current output IDs before filtering.
  4. Increment metadata counter `tweets_skipped_as_duplicates` by dropped rows count.
  5. Keep existing status/row_count updates and print statements intact.
- **Verification:** `uv run pytest tests/data_platform/ingestion/test_sync_twitter_checkpoint.py -q`

### TW-D2 — Twitter ingestion checkpoint tests
- **Verification:** `uv run pytest tests/data_platform/ingestion/test_sync_twitter_checkpoint.py -q`

### TW-D3 — Scale config creation
- **dataset_id:** `twitter_a8f3c22d-6b14-4e9a-9d2f-1c7e5a9b3d48`
- **Verification:** `PYTHONPATH=. uv run python data_platform/ingestion/sync_twitter.py --config mirrorview_scale.yaml --help`

## Integration Order
1. TW-D1 (code) → TW-D2 (tests).
2. Run ingestion test suite for Twitter checkpoint.
3. TW-D3 config creation.
4. Execute pipeline commands on scale dataset.
5. Collect outputs and metadata checks.

## Manual Verification
- [ ] Unit tests (Twitter ingestion dedupe):
  - `uv run pytest tests/data_platform/ingestion/test_sync_twitter_checkpoint.py -q`
- [ ] Existing Twitter downstream suites still green:
  - `uv run pytest tests/data_platform/preprocessing/test_preprocess_twitter.py tests/data_platform/generate_features/test_generate_twitter_features.py tests/data_platform/curate/test_curate_twitter.py -q`
- [ ] Lint/type checks:
  - `uv run pre-commit run --all-files`
- [ ] Ingestion scale run:
  - `PYTHONPATH=. uv run python data_platform/ingestion/sync_twitter.py --config mirrorview_scale.yaml`
- [ ] If interrupted, resume:
  - `PYTHONPATH=. uv run python data_platform/ingestion/sync_twitter.py --config mirrorview_scale.yaml --resume`
- [ ] Validate raw metadata:
  - `jq '.row_count, .sync_status, .tweets_skipped_as_duplicates // 0' data_platform/data/twitter/twitter_a8f3c22d-6b14-4e9a-9d2f-1c7e5a9b3d48/raw/<timestamp>/metadata.json`
- [ ] Preprocess:
  - `PYTHONPATH=. uv run python data_platform/preprocessing/preprocess_twitter.py --dataset-id twitter_a8f3c22d-6b14-4e9a-9d2f-1c7e5a9b3d48`
- [ ] Features smoke then full (see cursor plan for full commands).
- [ ] Curate:
  - `PYTHONPATH=. uv run python data_platform/curate/curate_twitter.py --dataset-id twitter_a8f3c22d-6b14-4e9a-9d2f-1c7e5a9b3d48 --config mirrorview.yaml`

## Alternative approaches
- **Operational-only (`--resume` single run) without code changes:** rejected.
- **Global cross-dataset dedupe index:** rejected.
- **Chosen approach:** Reddit pattern + one config flag + minimal Twitter ingestion diff.

## Final Verification
1. All new Twitter ingestion tests pass.
2. Existing Twitter preprocess/features/curate tests pass unchanged.
3. Pre-commit passes.
4. Scale ingestion reaches expected row budget and records duplicate skips.
5. Downstream stages complete and produce expected artifacts for the scale dataset.
