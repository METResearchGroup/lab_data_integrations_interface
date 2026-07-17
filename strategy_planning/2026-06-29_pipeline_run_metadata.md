<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Pipeline run metadata (2026-06-29)](#pipeline-run-metadata-2026-06-29)
  - [Two distinct concerns](#two-distinct-concerns)
  - [Stage run ID](#stage-run-id)
  - [Pipeline run record](#pipeline-run-record)
    - [Example: successful pipeline](#example-successful-pipeline)
    - [Example: pipeline X fails at feature generation](#example-pipeline-x-fails-at-feature-generation)
    - [Example: pipeline Y runs next (the recovery)](#example-pipeline-y-runs-next-the-recovery)
  - [Orchestrator behavior](#orchestrator-behavior)
  - [Storage](#storage)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Pipeline run metadata (2026-06-29)

Design for run-level metadata and pipeline run IDs across the ingestion → preprocessing → feature generation → curation pipeline.

---

## Two distinct concerns

Two questions look similar but are different:

- **Which orchestrator invocation triggered this stage execution?** → answered by the pipeline run record
- **What data flowed through this stage and where did it come from?** → answered by `source_*_runs` in stage-level `metadata.json`

These must not be conflated. The pipeline run record is about orchestrator invocations. Data lineage is about stage-level provenance and is already tracked by the `source_*_runs` fields that exist in each stage's `metadata.json`.

---

## Stage run ID

Each stage run's existing timestamp directory name (e.g. `raw/2026_06_27-00:50:27`) already serves as the stage run ID — it is unique, immutable, and created fresh on each new execution. No separate UUID is needed at the stage level.

The timestamp is surfaced as an explicit `run_id` field in each stage's `metadata.json` so it can be read without parsing directory paths.

---

## Pipeline run record

Do NOT put a `pipeline_run_id` on individual stage `metadata.json` files. The attribution would be misleading: a feature generation run may consume preprocessed data that was produced by a prior pipeline invocation, and tagging it with the current pipeline's ID would imply it did all the work.

Instead, maintain a **separate pipeline run record** per orchestrator invocation. This record lists only the stage runs that THIS invocation triggered.

### Example: successful pipeline

```json
{
  "pipeline_run_id": "f3a1b2c4-9d6e-4f2a-b8c1-3e5d7a9f0b2e",
  "dataset_id": "bluesky_9ea63f70-e9a2-4033-887d-97dcc43a0dc2",
  "started_at": "2026_06_27-00:50:27",
  "completed_at": "2026_06_27-01:14:23",
  "status": "completed",
  "stages": {
    "ingestion":     { "run_id": "2026_06_27-00:50:27", "status": "completed" },
    "preprocessing": { "run_id": "2026_06_27-00:53:05", "status": "completed" },
    "features":      { "run_id": "2026_06_27-01:00:00", "status": "completed" },
    "curation":      { "run_id": "2026_06_27-01:14:23", "status": "completed" }
  }
}
```

### Example: pipeline X fails at feature generation

```json
{
  "pipeline_run_id": "a1b2c3d4-...",
  "dataset_id": "bluesky_9ea63f70-e9a2-4033-887d-97dcc43a0dc2",
  "started_at": "2026_06_27-02:00:00",
  "completed_at": "2026_06_27-02:10:00",
  "status": "failed",
  "stages": {
    "ingestion":     { "run_id": "2026_06_27-02:00:00", "status": "completed" },
    "preprocessing": { "run_id": "2026_06_27-02:03:00", "status": "completed" },
    "features":      { "run_id": null, "status": "failed", "error": "Claude API timeout" },
    "curation":      { "run_id": null, "status": "not_started" }
  }
}
```

Pipeline X's ingestion and preprocessed runs are uploaded to S3. Features and curation never ran.

### Example: pipeline Y runs next (the recovery)

```json
{
  "pipeline_run_id": "e5f6a7b8-...",
  "dataset_id": "bluesky_9ea63f70-e9a2-4033-887d-97dcc43a0dc2",
  "started_at": "2026_06_27-03:00:00",
  "completed_at": "2026_06_27-03:20:00",
  "status": "completed",
  "stages": {
    "ingestion":     { "run_id": "2026_06_27-03:00:00", "status": "completed" },
    "preprocessing": { "run_id": "2026_06_27-03:03:00", "status": "completed" },
    "features":      { "run_id": "2026_06_27-03:10:00", "status": "completed" },
    "curation":      { "run_id": "2026_06_27-03:18:00", "status": "completed" }
  }
}
```

Pipeline Y's feature generation run consumed preprocessed data from BOTH pipeline X's preprocessed run AND pipeline Y's preprocessed run. Pipeline Y does not claim credit for X's ingestion or preprocessing — those appear only in X's pipeline run record. The data lineage for features (which preprocessed runs it consumed) is recorded in the feature stage's own `metadata.json` via `source_preprocessed_runs`, not in the pipeline run record.

---

## Orchestrator behavior

The orchestrator:

1. Generates a `pipeline_run_id` (UUID) at flow start
2. Runs each stage sequentially
3. After each stage — whether it succeeded or failed — writes/updates the pipeline run record
4. On stage failure: marks the stage `failed`, marks the overall pipeline `failed`, and stops. No retry within the same invocation.
5. Recovery is left entirely to the next orchestrator invocation, which generates a new `pipeline_run_id` and re-runs the full flow. Each stage's own resume/dedup/gate logic determines what work actually needs doing.

Writing the record after each stage (not just at the end) ensures a partial record exists even if the orchestrator process itself crashes mid-flow.

The orchestrator is stateless with respect to prior failures — it does not inspect prior pipeline run records to decide where to resume. All recovery intelligence lives in the individual stages.

---

## Storage

Pipeline run records can be stored as a `pipeline_runs.json` at the dataset root (alongside `dataset.json`), or in DynamoDB for low-latency querying without S3 reads. The `metadata.json` files inside each stage run directory remain unchanged — they record stage-level provenance only.
