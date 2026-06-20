# Pipeline improvement tickets (2026-06-19)

Pipeline stages: **ingestion → preprocessing → feature generation → curation**

---

## 1. Deduplication at each step

### [DEDUP-1] Register Glue partition after ingestion URI upload
After `upload_seen_uris` succeeds, call `ALTER TABLE dedupe_seen_ids ADD IF NOT EXISTS PARTITION` so Athena can see the new `dataset_id` partition. Without this, the next run's `load_seen_ids_from_athena` silently returns nothing for this dataset.
**Status**: not done

### [DEDUP-2] Create Glue table for preprocessed posts + add dedup at preprocessing
Preprocessing currently runs against whatever is in the local raw run dir. To deduplicate against already-preprocessed records across runs, we need a Glue table for preprocessed posts and a query at preprocessing time (analogous to `load_seen_ids_from_athena` at ingestion).
**Depends on**: S3-PREPROCESS-1, GLUE-2

### [DEDUP-3] Create Glue table for curated posts + add dedup at curation
Same pattern as DEDUP-2 but for the curation stage. Before curating, query Athena for post IDs already in the curated table and skip them.
**Depends on**: S3-CURATED-1, GLUE-4

### [DEDUP-4] Verify feature generation dedup covers S3-resident labels
`filter_records_needing_features` already dedupes against label files on local disk. Verify (or extend) this to also check S3-resident label files from prior runs so features aren't recomputed after local cleanup.
**Depends on**: S3-FEATURES-1

---

## 2. S3 uploads at each step

### [S3-RAW-1] Upload raw posts to S3 after ingestion
Upload the raw CSV run dir to S3 under `raw/platform=bluesky/dataset_id=<id>/run=<timestamp>/`. Currently only URIs are uploaded; raw posts themselves are not.
**Depends on**: GLUE-1

### [S3-RAW-2] Register Glue partition for raw posts after upload
After S3-RAW-1 upload, call `ALTER TABLE raw_posts ADD IF NOT EXISTS PARTITION`.

### [S3-PREPROCESS-1] Upload preprocessed posts to S3 after preprocessing
After `preprocess_records` succeeds, upload the output CSV to S3 under `preprocessed/platform=bluesky/dataset_id=<id>/run=<timestamp>/`.
**Depends on**: GLUE-2

### [S3-PREPROCESS-2] Register Glue partition for preprocessed posts after upload

### [S3-FEATURES-1] Upload feature label files to S3 after feature generation
After `generate_features` succeeds, upload per-feature CSVs to S3 under `features/<feature_name>/platform=bluesky/dataset_id=<id>/run=<timestamp>/`.
**Depends on**: GLUE-3

### [S3-FEATURES-2] Register Glue partitions for feature labels after upload

### [S3-CURATED-1] Create Glue table for curated posts + register partition after postprocessing
`postprocess_bluesky.py` already uploads to S3 but no Glue table exists and no partition is registered. Add both.
**Depends on**: GLUE-4

---

## 3. Glue tables in Terraform (prerequisite for several tickets above)

### [GLUE-1] Define Glue table for raw posts
Partition keys: `platform`, `dataset_id`, `run`. Covers `raw/` S3 prefix.

### [GLUE-2] Define Glue table for preprocessed posts
Partition keys: `platform`, `dataset_id`, `run`. Covers `preprocessed/` S3 prefix.

### [GLUE-3] Define Glue table(s) for feature labels
Either one table per feature or a unified table with `feature_name` as an additional partition key. Covers `features/` S3 prefix.

### [GLUE-4] Define Glue table for curated posts
Partition keys: `platform`, `dataset_id`. Covers `curated/` S3 prefix.

---

## 4. Metadata uploads at each step

### [META-1] Design and provision DynamoDB table for run-level metadata
Define PK/SK structure (e.g., `dataset_id` PK + `run_id` SK), fields (`status`, `last_stage`, `start_time`, `end_time`, `error`), and Terraform resource. This is a prerequisite for META-2 through META-5.

### [META-2] Write run metadata to DynamoDB after ingestion
After `sync_records` completes, write a record: `dataset_id`, `run_id`, `sync_status`, `row_count`, timestamps.

### [META-3] Write run metadata to DynamoDB after preprocessing
After `preprocess_records` completes, update/write the run record with preprocessing status and output row count.

### [META-4] Write run metadata to DynamoDB after feature generation
After `generate_features` completes, update/write the run record with feature generation status.

### [META-5] Write run metadata to DynamoDB after curation
After `postprocess_bluesky` completes, update/write the run record with curation status.

### [META-6] Upload metadata.json to S3 alongside data files at each stage
Simple archival — copy the local `metadata.json` to S3 with the rest of the stage's artifacts. Cheap audit trail independent of DynamoDB.

---

## 5. Local disk cleanup

### [CLEANUP-1] Delete local raw files after successful S3 upload + partition registration
Gate deletion on both the S3 upload and the Glue partition registration succeeding. Raw files are the largest artifact and earliest candidate for cleanup.
**Depends on**: S3-RAW-1, S3-RAW-2

### [CLEANUP-2] Delete local preprocessed files after successful S3 upload
**Depends on**: S3-PREPROCESS-1, S3-PREPROCESS-2

### [CLEANUP-3] Delete local feature label files after successful S3 upload
**Depends on**: S3-FEATURES-1, S3-FEATURES-2

### [CLEANUP-4] Extend curation cleanup to cover all local stage dirs
`postprocess_bluesky.py` currently only deletes the raw dir. Extend to clean up preprocessed, feature, and curated local dirs after all S3 uploads succeed.
**Depends on**: CLEANUP-1, CLEANUP-2, CLEANUP-3
