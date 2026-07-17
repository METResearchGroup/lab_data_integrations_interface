<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Data Platform Progress Summary — 2026-06-10](#data-platform-progress-summary--2026-06-10)
  - [Work Completed](#work-completed)
  - [Data Pipeline Overview (Current)](#data-pipeline-overview-current)
    - [1. Ingestion](#1-ingestion)
    - [2. Preprocessing](#2-preprocessing)
    - [3. Feature Generation](#3-feature-generation)
    - [4. Curation](#4-curation)
  - [Open Questions / In Progress](#open-questions--in-progress)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Data Platform Progress Summary — 2026-06-10

## Work Completed

- Ran the pipeline on the Trump job
- Started working on S3 sync, but realized we may want to upload more than just posts to S3
- Experimented with dedupe logic; decided to store files containing only post IDs and query from those in the ingestion step
- Experimented with S3 + SQLite, Athena, DuckDB, and DynamoDB
- Changed dedupe logic to use Athena
- S3 sync (not merged yet)

---

## Data Pipeline Overview (Current)

### 1. Ingestion

Calls the Bluesky API with the same query each time, up to a limit of the most recent posts. Deduplicates against two sources:

- The current run's own timestamped directory on disk (`raw/<timestamp>/posts.csv`) — empty on a fresh run, partial data on a resume
- Athena, for cross-run deduplication

Writes to `raw/<timestamp>/posts.csv` and flushes `metadata.json` per task (audit trail only).

### 2. Preprocessing

Reads only the records file (`posts.(csv or parquet)`) from the single latest raw **COMPLETED** timestamped directory. Applies text/row validators to filter posts. Writes filtered records to `preprocessed/<timestamp>/posts.(csv or parquet)` plus a `metadata.json` (audit trail only, never read downstream). No deduplication.

### 3. Feature Generation

For each feature sequentially:

1. Reads the feature's flat file (`features/<feature_name>.csv`) to get already-labeled URIs
2. Creates an in-memory filtered view of the preprocessed posts keeping only unlabeled ones
3. Sends those to the LLM
4. Appends new labels to `features/<feature_name>.csv`

The preprocessed file is never modified. Tracks progress in `features/metadata.json`, flushed after each batch.

### 4. Curation

Reads `posts.csv` from the latest preprocessed timestamped directory, LEFT JOINs it against each flat `features/<feature_name>.csv` via DuckDB (one CTE per feature, deduped by URI within each file), applies filter rules, and writes the result to `curated/<timestamp>/`. No deduplication.


## Open Questions / In Progress

- Need to decouple each step from each other - have each step do deduplication
- No more uploading individual tables for S3 IDs, instead just query on the posts themselves
- Need to finish orchestration
- Start working on querying next (the actual querying backend; query types TBD)

