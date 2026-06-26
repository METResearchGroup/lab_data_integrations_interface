# Deduplication design (2026-06-25)

Decisions made about deduplication logic, dataset/run identity, and the auto-catch-up sweep across pipeline stages.

## Core identity model

### dataset_id — stable per config

`dataset_id` identifies a collection config (e.g., `bluesky_f47ac10b-...`). It is created once and reused across every run of that config. It does not change between daily runs, retries, or catch-up runs.

If the config changes (new queries, different columns, different platform), a new `dataset_id` is created. This is what guarantees that all runs under the same `dataset_id` have the same column schema — same config, same ingestion script, same fields.

### Timestamp — the run identity

Each execution of a pipeline stage creates a timestamped directory (e.g., `raw/2026_06_25-14:00:00/`). The timestamp is what identifies a specific run attempt, not the dataset.

This keeps `dataset_id` semantically meaningful ("what are we collecting") and the timestamp semantically meaningful ("when did we collect it / which attempt was this").

Making `dataset_id` 1:1 with a run was considered and rejected: it collapses two distinct concepts into one identifier, breaks cross-run deduplication, and makes historical queries require a config→[dataset_ids] mapping anyway.

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

## Auto-catch-up sweep

When a prior run fails partway, the next run sweeps up unprocessed upstream artifacts rather than requiring manual backfill. This was chosen over manual retries to reduce operational burden and to keep run IDs unambiguous (retrying a specific run ID would mean two executions share one ID, breaking its meaning).

### What "sweep" means at each stage

Each downstream stage finds all upstream run_dirs that have not yet been referenced in any of its own outputs' `source_X_runs` metadata. It merges those run_dirs, deduplicates by URI, and produces a single output with `source_X_runs: [T1, T2, ...]`.

```
Preprocessing sweep:
  pending_raw_runs = all raw/{timestamp}/ dirs
                   - union of source_raw_runs across all preprocessed/*/metadata.json

  if pending_raw_runs is empty: nothing to do
  else: merge + dedup → preprocessed/{now}/
```

Same pattern for curation over preprocessed runs.

**Sweep is always scoped to the current `dataset_id`.** Different datasets are never mixed, even if they share the same config file. Column schema consistency within a sweep is guaranteed by this scoping.

### Consumed tracking

The sweep relies on `source_X_runs` lists in each stage's `metadata.json`. These files are the provenance record and must not be deleted during disk cleanup, even if the associated data files are removed.

## Features: partitioned by preprocessed run

Features are an exception to the flat timestamped-directory pattern used by other stages.

### Why partitioned

Features are keyed by URI. Since preprocessing dedup guarantees each URI appears exactly once across all preprocessed outputs, features can be stored as an accumulative lookup table rather than a per-run snapshot. There is no need to timestamp the feature directory itself.

However, storing features as a single flat file creates upload problems at scale (re-uploading millions of rows when only thousands are new) and loses the association between labels and the preprocessed run that produced them.

**Decision**: partition features by the preprocessed run that generated them, both locally and on S3.

```
# Local
features/
  preprocessed_run=T1/is_political.parquet
  preprocessed_run=T2/is_political.parquet

# S3
s3://.../features/
  platform=bluesky/
    feature=is_political/
      dataset_id=bluesky_abc123/
        preprocessed_run=T1/part.parquet
        preprocessed_run=T2/part.parquet
```

### Benefits

- Uploads are incremental — each run only uploads its own partition (the new labels), not the full history.
- Feature partitions are never overwritten by subsequent runs.
- If curation fails after feature generation and a new run comes in, the original feature partition for the failed run is still intact.
- Athena queries across all partitions transparently as one table.

### Feature dedup

"Unlabeled records" = URIs in the current preprocessed batch not present in any existing feature partition. Warm-up loads all URIs across all feature partitions into a set (same disk + Athena pattern). At current scale this is fine; at scale, replace the disk scan with an Athena query.

## S3 retry sweep

If a stage completes locally but its S3 upload fails (`s3_upload_status: false`), Athena does not know about those records. The next run's Athena warm-up will miss them, and ingestion may re-collect the same URIs.

**Decision**: at the start of each run, before any new work begins, scan for prior stage run_dirs with `s3_upload_status: false` and retry those uploads. Only after all pending uploads are resolved does the new run proceed.

This keeps S3 as the reliable source of truth and ensures Athena warm-ups are accurate before dedup runs.

## Open questions

| Question | Status |
|----------|--------|
| Is local metadata scan sufficient for sweep, or does consumed tracking need to be in DynamoDB? | Open |
| For feature dedup warm-up, load all partition URIs into set (disk) or query Athena? | Defer until scale is a concern |
| Should S3 retry sweep also verify against S3 directly, or trust `s3_upload_status` in local metadata? | Open |
