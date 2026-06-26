# Deduplication design (2026-06-25)

Decisions made about deduplication logic, dataset/run identity, and gate checks across pipeline stages.

## Core identity model

### dataset_id — stable per config

`dataset_id` identifies a collection config (e.g., `bluesky_f47ac10b-...`). It is created once and reused across every run of that config. It does not change between daily runs, retries, or catch-up runs.

If the config changes (new queries, different columns, different platform), a new `dataset_id` is created. This is what guarantees that all runs under the same `dataset_id` have the same column schema — same config, same ingestion script, same fields.

### Timestamp — the run identity

Each execution of a pipeline stage creates a timestamped directory (e.g., `raw/2026_06_25-14:00:00/`). The timestamp is what identifies a specific run attempt, not the dataset.

This keeps `dataset_id` semantically meaningful ("what are we collecting") and the timestamp semantically meaningful ("when did we collect it / which attempt was this").

Making `dataset_id` 1:1 with a run was considered and rejected: it collapses two distinct concepts into one identifier, breaks cross-run deduplication, and makes historical queries require a config→[dataset_ids] mapping anyway.

## Startup sequence at every stage

Every stage follows the same startup order before doing any new work:

```
1. Gate check       — hard fail if any upstream run is not fully complete
2. DedupeSession.warm() — load seen IDs from disk + Athena
3. Do the work
```

## Dedup at each stage

Dedup is applied at every stage, not just ingestion. A record passing through one stage does not guarantee its downstream outputs exist.

The warm-up pattern is the same at every stage:

1. **Disk** — load IDs from the current run's output file. Handles resume-within-a-run: if the process crashed and restarted mid-run, already-written records are not re-written.
2. **Athena** — query the stage table for all URIs under this `dataset_id`. Handles cross-run historical dedup.

```
DedupeSession.warm():
  seen_ids = load_seen_ids_from_disk(current_run_dir)  # resume safety
            + load_seen_ids_from_athena()               # historical
```

The disk component is narrow (current run only). Athena is the source of truth for history. This works as long as S3 uploads are reliable — see S3 retry sweep below.

### Stage dedup targets

| Stage | ID column | Athena table |
|-------|-----------|--------------|
| Ingestion → Raw | `uri` | `bluesky_raw` |
| Raw → Preprocessed | `uri` | `bluesky_preprocessed` |
| Preprocessed → Features | `uri` | `bluesky_features` |
| Preprocessed → Curated | `uri` | `bluesky_curated` |

All scoped to `WHERE dataset_id = '{dataset_id}'`.

## Gate checks per stage

Each stage hard fails if its upstream is not fully complete. "Complete" means both `sync_status: completed` and `s3_upload_status: true`. Each stage is responsible for its own S3 upload reliability — if a stage's upload fails, it is marked incomplete and a human re-runs that stage before downstream can proceed.

### Preprocessing gate

Checks **all** `raw/{timestamp}/` dirs for this `dataset_id`. If any raw run is not complete, hard fail. There is no concept of "only check the latest" — every raw run must be clean before preprocessing proceeds.

### Feature generation gate

Checks **all** `preprocessed/{timestamp}/` dirs for this `dataset_id`. If any preprocessed run is not complete, hard fail.

### Curation gate

Checks two things:
1. **All** `preprocessed/{timestamp}/` dirs complete
2. Features `s3_upload_status: true` in `features/metadata.json`

Both must pass before curation proceeds. Curation joins preprocessed records with feature labels; any incomplete upstream produces a corrupt or missing join.

## Sweep model

Each downstream stage always loads **all** upstream run dirs for this `dataset_id`, not just the ones it hasn't seen before. The `DedupeSession` Athena warm-up is what prevents re-processing — URIs already present in the downstream Athena table are filtered out, so only genuinely new records flow through.

This is simpler than tracking consumed runs explicitly: no `pending = all - union(source_X_runs)` diff is needed. If the Athena table has complete data (guaranteed by the S3 retry sweep and gate check), the warm-up naturally skips already-processed URIs.

`source_raw_runs` in preprocessed `metadata.json` is still written as a **provenance record** (which raw runs contributed to this preprocessed output), but it does not gate what gets processed.

**Sweep is always scoped to the current `dataset_id`.** Different datasets are never mixed.

## Features: flat accumulative store per dataset

Features are an exception to the timestamped-directory pattern used by other stages. There is no `features/{timestamp}/` directory — features are stored as a flat set of files directly under `features/`, one file per feature label.

```
features/
  is_political.parquet
  is_toxic_tiered.parquet
  is_self_contained.parquet
  metadata.json
```

### Why flat

Features are keyed by URI. Preprocessing dedup guarantees each URI appears exactly once across all preprocessed outputs, so feature files accumulate without collision — new URIs are appended, existing ones are never re-labeled. There is no need to version or partition the feature files by which preprocessed run produced them.

### Sweep model for features

Feature generation sweeps **all** preprocessed runs for this `dataset_id`, not just the latest:

1. Gate check — all `preprocessed/{timestamp}/` dirs must have `s3_upload_status: true`
2. DedupeSession warm-up — scan all existing feature files (disk) + query Athena features table scoped to `dataset_id`. Any URI already present is skipped.
3. Load all preprocessed records across all runs
4. Filter to unlabeled URIs only
5. Generate features for the remainder and append to the flat feature files
6. Upload updated feature files to S3, set `s3_upload_status: true` in `metadata.json`

The feature files themselves are the record of what has been labeled. No separate "which preprocessed runs are done" tracking is needed — if a URI is in the feature files, it is labeled regardless of which preprocessed run it came from.

## Open questions

| Question | Status |
|----------|--------|
| For feature dedup warm-up, load all feature file URIs into set (disk) or query Athena? | Disk scan is fine at current scale — switch to Athena-only when disk scan becomes slow |
