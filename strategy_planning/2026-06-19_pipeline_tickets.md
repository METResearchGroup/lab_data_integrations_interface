<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Pipeline improvement tickets (2026-06-19)](#pipeline-improvement-tickets-2026-06-19)
  - [PR 1: Glue tables (Terraform)](#pr-1-glue-tables-terraform)
    - [[GLUE-1] Define Glue table for raw posts](#glue-1-define-glue-table-for-raw-posts)
    - [[GLUE-2] Define Glue table for preprocessed posts](#glue-2-define-glue-table-for-preprocessed-posts)
    - [[GLUE-3] Define Glue table(s) for feature labels](#glue-3-define-glue-tables-for-feature-labels)
    - [[GLUE-4] Define Glue table for curated posts](#glue-4-define-glue-table-for-curated-posts)
  - [PR 2: S3 uploads at each step](#pr-2-s3-uploads-at-each-step)
    - [[S3-1] Register Glue partition after ingestion URI upload](#s3-1-register-glue-partition-after-ingestion-uri-upload)
    - [[S3-2] Upload raw posts to S3 after ingestion + register partition](#s3-2-upload-raw-posts-to-s3-after-ingestion--register-partition)
    - [[S3-3] Upload preprocessed posts to S3 after preprocessing + register partition](#s3-3-upload-preprocessed-posts-to-s3-after-preprocessing--register-partition)
    - [[S3-4] Upload feature label files to S3 after feature generation + register partitions](#s3-4-upload-feature-label-files-to-s3-after-feature-generation--register-partitions)
    - [[S3-5] Upload curated posts to S3 after curation + register partition](#s3-5-upload-curated-posts-to-s3-after-curation--register-partition)
  - [PR 3: Deduplication at each step](#pr-3-deduplication-at-each-step)
    - [[DEDUP-1] Add dedup at preprocessing against Athena preprocessed table](#dedup-1-add-dedup-at-preprocessing-against-athena-preprocessed-table)
    - [[DEDUP-2] Add dedup at curation against Athena curated table](#dedup-2-add-dedup-at-curation-against-athena-curated-table)
    - [[DEDUP-3] Verify feature generation dedup covers S3-resident labels](#dedup-3-verify-feature-generation-dedup-covers-s3-resident-labels)
  - [PR 4: Metadata uploads at each step](#pr-4-metadata-uploads-at-each-step)
    - [[META-1] Design and provision DynamoDB table for run-level metadata](#meta-1-design-and-provision-dynamodb-table-for-run-level-metadata)
    - [[META-2] Write run metadata to DynamoDB after ingestion](#meta-2-write-run-metadata-to-dynamodb-after-ingestion)
    - [[META-3] Write run metadata to DynamoDB after preprocessing](#meta-3-write-run-metadata-to-dynamodb-after-preprocessing)
    - [[META-4] Write run metadata to DynamoDB after feature generation](#meta-4-write-run-metadata-to-dynamodb-after-feature-generation)
    - [[META-5] Write run metadata to DynamoDB after curation](#meta-5-write-run-metadata-to-dynamodb-after-curation)
    - [[META-6] Upload metadata.json to S3 alongside data files at each stage](#meta-6-upload-metadatajson-to-s3-alongside-data-files-at-each-stage)
  - [PR 5: Local disk cleanup](#pr-5-local-disk-cleanup)
    - [[CLEANUP-1] Delete local raw files after successful S3 upload + partition registration](#cleanup-1-delete-local-raw-files-after-successful-s3-upload--partition-registration)
    - [[CLEANUP-2] Delete local preprocessed files after successful S3 upload](#cleanup-2-delete-local-preprocessed-files-after-successful-s3-upload)
    - [[CLEANUP-3] Delete local feature label files after successful S3 upload](#cleanup-3-delete-local-feature-label-files-after-successful-s3-upload)
    - [[CLEANUP-4] Extend curation cleanup to cover all local stage dirs](#cleanup-4-extend-curation-cleanup-to-cover-all-local-stage-dirs)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Pipeline improvement tickets (2026-06-19)

Pipeline stages: **ingestion → preprocessing → feature generation → curation**

---

## PR 1: Glue tables (Terraform)

All Glue catalog tables needed for subsequent PRs. No Python changes.

### [GLUE-1] Define Glue table for raw posts
Partition keys: `platform`, `dataset_id`, `run`. Covers `raw/` S3 prefix.

### [GLUE-2] Define Glue table for preprocessed posts
Partition keys: `platform`, `dataset_id`, `run`. Covers `preprocessed/` S3 prefix.

### [GLUE-3] Define Glue table(s) for feature labels
Either one table per feature or a unified table with `feature_name` as an additional partition key. Covers `features/` S3 prefix.

### [GLUE-4] Define Glue table for curated posts
Partition keys: `platform`, `dataset_id`. Covers `curated/` S3 prefix.

---

## PR 2: S3 uploads at each step

### [S3-1] Register Glue partition after ingestion URI upload
After `upload_seen_uris` succeeds, call `ALTER TABLE dedupe_seen_ids ADD IF NOT EXISTS PARTITION`. This is already missing and silently breaks Athena dedup.

### [S3-2] Upload raw posts to S3 after ingestion + register partition
Upload the raw CSV run dir to `raw/platform=bluesky/dataset_id=<id>/run=<timestamp>/` and register the partition.

### [S3-3] Upload preprocessed posts to S3 after preprocessing + register partition
After `preprocess_records` succeeds, upload output CSV to `preprocessed/platform=bluesky/dataset_id=<id>/run=<timestamp>/` and register partition.

### [S3-4] Upload feature label files to S3 after feature generation + register partitions
After `generate_features` succeeds, upload per-feature CSVs to `features/<feature_name>/platform=bluesky/dataset_id=<id>/run=<timestamp>/` and register partitions.

### [S3-5] Upload curated posts to S3 after curation + register partition
`postprocess_bluesky.py` already uploads files but no partition is registered. Add partition registration after upload.

---

## PR 3: Deduplication at each step

### [DEDUP-1] Add dedup at preprocessing against Athena preprocessed table
Before preprocessing, query Athena for post IDs already in the preprocessed table and skip them. Analogous to `load_seen_ids_from_athena` at ingestion.
**Depends on**: PR 1 (GLUE-2), PR 2 (S3-3)

### [DEDUP-2] Add dedup at curation against Athena curated table
Before curating, query Athena for post IDs already in the curated table and skip them.
**Depends on**: PR 1 (GLUE-4), PR 2 (S3-5)

### [DEDUP-3] Verify feature generation dedup covers S3-resident labels
`filter_records_needing_features` already dedupes against local label files. Verify/extend to also cover S3-resident labels from prior runs so features aren't recomputed after local disk cleanup.
**Depends on**: PR 2 (S3-4)

---

## PR 4: Metadata uploads at each step

### [META-1] Design and provision DynamoDB table for run-level metadata
Define PK/SK structure (e.g., `dataset_id` PK + `run_id` SK), fields (`status`, `last_stage`, `start_time`, `end_time`, `error`), and Terraform resource. Prerequisite for META-2 through META-5.

### [META-2] Write run metadata to DynamoDB after ingestion
After `sync_records` completes, write: `dataset_id`, `run_id`, `sync_status`, `row_count`, timestamps.

### [META-3] Write run metadata to DynamoDB after preprocessing

### [META-4] Write run metadata to DynamoDB after feature generation

### [META-5] Write run metadata to DynamoDB after curation

### [META-6] Upload metadata.json to S3 alongside data files at each stage
Copy local `metadata.json` to S3 with the rest of each stage's artifacts. Cheap audit trail independent of DynamoDB.

---

## PR 5: Local disk cleanup

### [CLEANUP-1] Delete local raw files after successful S3 upload + partition registration
Gate deletion on both S3 upload and Glue partition registration succeeding.
**Depends on**: PR 2 (S3-2)

### [CLEANUP-2] Delete local preprocessed files after successful S3 upload
**Depends on**: PR 2 (S3-3)

### [CLEANUP-3] Delete local feature label files after successful S3 upload
**Depends on**: PR 2 (S3-4)

### [CLEANUP-4] Extend curation cleanup to cover all local stage dirs
`postprocess_bluesky.py` currently only deletes the raw dir. Extend to clean up preprocessed, feature, and curated local dirs once all S3 uploads succeed.
**Depends on**: CLEANUP-1, CLEANUP-2, CLEANUP-3
