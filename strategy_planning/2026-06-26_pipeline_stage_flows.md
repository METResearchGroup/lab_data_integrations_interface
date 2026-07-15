<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Pipeline stage flows (2026-06-26)](#pipeline-stage-flows-2026-06-26)
  - [Ingestion](#ingestion)
  - [Preprocessing](#preprocessing)
  - [Feature generation](#feature-generation)
  - [Curation](#curation)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Pipeline stage flows (2026-06-26)

Detailed execution flow for each pipeline stage, capturing deduplication, gate checks, resume logic, and early-exit conditions.

---

## Ingestion

1. **Resume check** — scan all `raw/{timestamp}/` dirs for this `dataset_id`. Find the most recent one with `s3_upload_status: false`. If found, resume that dir (do not create a new one).
2. **New run** — if no resumable dir exists, create a new `raw/{timestamp}/` dir and initialize `metadata.json` with `sync_status: in_progress`, `s3_upload_status: false`.
3. **Checkpointed task loop** — iterate all tasks (e.g. per-keyword queries). Skip any task already marked `completed` or `skipped`. Re-run anything `pending`, `in_progress`, or `failed`.
4. **DedupeSession** — before each task, `warm()` loads seen IDs from disk (current run dir CSV) + Athena (`bluesky_raw` table, scoped to `dataset_id`). Records already seen are filtered out before writing.
5. **Finalize** — after all tasks complete, compute `sync_status` from task statuses. If `completed`, upload CSV to S3 and set `s3_upload_status: true`.

**Resume trigger:** `s3_upload_status: false` on an existing run dir. Covers both mid-collection crashes (tasks not done) and completed-collection-but-upload-failed cases. `run_checkpointed_sync` skips already-completed tasks either way, so resuming always does the right thing.

---

## Preprocessing

1. **Upload retry sweep** — scan all `preprocessed/{timestamp}/` dirs for this `dataset_id`. For each with `s3_upload_status: false` AND the output CSV exists on disk, retry the S3 upload and mark `s3_upload_status: true`. This must happen before the DedupeSession warm-up so Athena has accurate data.

2. **Gate check** — call `raw_storage.all_runs_uploaded()`. Hard fail if any `raw/{timestamp}/` dir has `s3_upload_status: false`. Each raw run must be fully uploaded before preprocessing proceeds.

3. **DedupeSession warm-up** — load seen URIs from:
   - Disk: current preprocessed run dir output file (handles mid-write resume)
   - Athena: `bluesky_preprocessed` table scoped to `dataset_id`

4. **Load all raw runs** — load records from every `raw/{timestamp}/` dir for this `dataset_id`. Always all runs, never just the latest.

5. **Filter** — run text and row validators (length, language, URL, etc.) to remove low-quality records.

6. **Dedup** — filter out any URIs already in the DedupeSession `seen_ids`. These are URIs already present in a prior preprocessed run (via Athena) or in the current partial output (via disk).

7. **Early exit** — if 0 records remain after dedup, do not create a new run dir. Return `None`. The pipeline continues; downstream stages will similarly find nothing new to do.

8. **Write output** — create a new `preprocessed/{timestamp}/` dir, write filtered records to CSV, write `metadata.json` with `s3_upload_status: false` and `source_raw_runs` (provenance only).

9. **Upload** — upload CSV to S3, set `s3_upload_status: true`.

**No new run dir is created if there is nothing to preprocess.** This prevents accumulation of empty dirs and keeps downstream gate checks clean.

`source_raw_runs` in `metadata.json` records which raw run dirs contributed to this output for provenance, but is not used to determine what to process — the DedupeSession Athena warm-up handles that.

---

## Feature generation

Features are stored as a flat accumulative set of files directly under `features/` — one parquet file per feature label (e.g. `is_political.parquet`). There are no timestamped subdirectories. The feature files grow over time as new preprocessed records are labeled. A single `features/metadata.json` tracks overall status and `s3_upload_status`.

1. **Upload retry sweep** — if `features/metadata.json` exists and `s3_upload_status: false`, and the feature files exist on disk, retry the S3 upload and mark `s3_upload_status: true` before proceeding. This ensures Athena has accurate data before the DedupeSession warm-up.

2. **Gate check** — call `preprocessed_storage.all_runs_uploaded()`. Hard fail if any `preprocessed/{timestamp}/` dir has `s3_upload_status: false`. All preprocessed runs must be fully uploaded before feature generation proceeds.

3. **Dedup warm-up** — per feature, load labeled URIs from:
   - Disk: read `features/{feature_name}.parquet` directly (flat file, no timestamped subdir)
   - Athena: `bluesky_features_{feature_name}` table (one table per feature), scoped to `dataset_id`

4. **Load all preprocessed runs** — load records from every `preprocessed/{timestamp}/` dir for this `dataset_id`. Always all runs.

5. **Dedup** — filter out any URIs already in the DedupeSession `seen_ids`. These are URIs already labeled in a prior feature generation run. The feature files themselves are the source of truth for what has been labeled — no separate run tracking is needed.

6. **Early exit** — if 0 unlabeled URIs remain, do nothing. Return early without modifying feature files or `metadata.json`.

7. **Generate and append** — run feature labeling for the unlabeled records and append new rows to the existing flat feature parquet files. Feature files are never rewritten from scratch — only new rows are appended.

8. **Upload** — upload each updated feature parquet to S3, register its Athena partition on `bluesky_features_{feature_name}` with `(platform, dataset_id)`, then set `s3_upload_status: true` in `features/metadata.json`. `s3_upload_status: true` implies both uploaded AND partition registered.

`features/metadata.json` also tracks `source_preprocessed_runs` — the list of all preprocessed run dirs that existed at generation time, for provenance only.

**The feature files are the record of what has been labeled.** If a URI is present in the feature files, it is labeled, regardless of which preprocessed run it came from. No per-run feature partitioning is needed.

---

## Curation

Curation joins all preprocessed records with their feature labels, applies business-rule filters, and exports the result. Output goes into a timestamped `curated/{timestamp}/` dir like raw and preprocessed.

1. **Upload retry sweep** — scan all `curated/{timestamp}/` dirs for this `dataset_id`. For each with `s3_upload_status: false` AND the output file exists on disk, retry S3 upload + register Athena partition, then mark `s3_upload_status: true`.

2. **Gate checks** — hard fail if either:
   - `preprocessed_storage.all_runs_uploaded()` is false — any preprocessed run not yet uploaded/partitioned
   - `features/metadata.json` `s3_upload_status` is false — features not yet uploaded/partitioned

   Both must be true before curation proceeds. Curation joins preprocessed records with feature labels; any incomplete upstream produces a corrupt or missing join.

3. **Early exit (run-level dedup)** — curation always produces a complete snapshot, not an accumulation of new records. URI-level dedup (like preprocessing's DedupeSession) does not apply here — there is no concept of "already curated this URI, skip it." Instead, dedup happens at the run level: skip creating a new curated run if the inputs haven't changed. Check if the latest curated run has `s3_upload_status: true`, its `source_preprocessed_runs` matches the current list of preprocessed run dirs, AND its `rules_hash` (sha256 of the rules config YAML) matches the current file. If all three conditions hold, return the existing output path immediately. If any differ (a new preprocessed run appeared, or the rules file was edited), proceed with a fresh run.

4. **Load all preprocessed runs** — load records from every `preprocessed/{timestamp}/` dir for this `dataset_id`. Concatenate into a single dataframe. Always all runs, never just the latest.

5. **Join with features** — read each flat feature parquet file from `features/` and join on URI. The flat store guarantees each URI has at most one label per feature regardless of which preprocessed run it came from.

6. **Apply curation rules** — run the configured filter steps (e.g. `mirrorview.yaml`). Each step removes records that fail a condition and records how many passed.

7. **Write output** — create a new `curated/{timestamp}/` dir, write the filtered output file, write `metadata.json` with `s3_upload_status: false`, `source_preprocessed_runs`, and `rules_hash` (for the next run's early-exit check).

8. **Upload** — upload the curated output file to S3, register its Athena partition on `bluesky_curated` with `(platform, dataset_id, run_dir)`, then set `s3_upload_status: true`.

`source_preprocessed_runs` and `rules_hash` in `metadata.json` serve double duty: provenance tracking AND inputs to the next run's early-exit check.
