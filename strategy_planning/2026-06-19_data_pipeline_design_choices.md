# Data pipeline design choices (2026-06-19)

What we decided for the pipeline, the tradeoffs we explicitly considered, and the concrete scenarios used to reason about correctness.

(AI-generated based on notes + call transcript)

## Pipeline shape (the “happy path”)

- **Stages**: ingestion → preprocessing → feature generation → curation
- **Interface for consumers**: query via **Athena** (tables in **Glue**) over data stored in **S3**
- **Why keep multiple stages**:
  - **Curated is opinionated** (e.g., filters toxicity / “not political enough”); other users may want **raw** or other views.

## Design choices made

### Store stage outputs in S3 (not just on disk)

- **Decision**: add an **S3 upload after each node/stage** (ingestion, preprocessing, feature generation, curation).
- **Rationale**:
  - Treat **S3 as the system of record** for each stage’s artifacts.
  - Makes downstream processing less fragile than relying on local disk scratch space.
  - Enables alternative views (raw vs curated) and supports future users/teams with different needs.

### Accept data duplication across stages (copy-on-write pipeline)

- **Decision**: it’s OK that preprocessing / feature generation may duplicate large portions of raw data in S3.
- **Tradeoff**:
  - **Pros**: reduces risk of **data loss**; simpler recovery and auditing; aligns with “classic data engineering pipelines” that materialize intermediate datasets.
  - **Cons**: higher storage footprint.
- **Reasoning captured in transcript**: “storage is cheap; loss of data is expensive.” If cost becomes a problem later, we can delete/compact old intermediates.

### Derive “seen IDs” from tables on demand (single source of truth)

- **Decision**: don’t maintain a separate “seen_ids” S3 dataset as the primary mechanism.
- **Instead**: **create/query tables on demand** (via Athena/Glue) to compute “seen IDs” from the canonical data.
- **Rationale**:
  - Preserves a **single source of truth** (avoid two drifting tables/datasets).
  - Avoids expensive “select every post ever” scans; we only need a bounded window.
- **Practical bound**: treat the system as **“idempotent up to ~the past 2 days”** by querying only recent partitions/windows for dedupe/seen-id checks (scales better + cheaper).

### Deduplicate at each node (not only at ingestion)

- **Decision**: do **dedupe checks at each stage**, not just ingestion.
- **Rationale**:
  - You can’t guarantee downstream inputs are deduped unless you **actually check at that stage**.
  - Protects against idempotency failures and race conditions when runs overlap.
- **Known limitation**:
  - Still not perfect due to TOCTOU-style races (two workers check “doesn’t exist” then both write). We accept this as an edge behavior that’s “likely not a big deal” for us right now, but dedupe-at-each-node is a stronger baseline.

### Choose “auto-catch-up” semantics for failed runs (Option 2)

- **Decision**: when a prior run fails partway, later runs should be able to **pick up posts that have not yet been processed at a given stage**, rather than relying on manual backfills of the failed run.
- **Rationale**:
  - **Less manual ops**: fix the bug, rerun the pipeline, and the next run “heals” missing downstream artifacts.
  - Avoids relying on engineers to notice failures and manually rerun specific historical run folders.
- **Tradeoff framing used in discussion**: **maintainability vs control**.
  - Option 1 (manual retries) gives more explicit control but requires operational work. Also Option 1 allows for multiple runs to exist with the same ID, which isn't desirable.
  - Option 2 reduces manual work but gives up some “control” and forces a richer provenance model.
- **Consequence**: requires a **more complex provenance model** (see below), because one stage’s run can “collapse” multiple upstream runs’ data.

## Provenance, run IDs, and metadata

### Run ID semantics: keep run IDs idempotent / meaningful

- **Key point**: a major strike against “manual rerun of run 1” (Option 1) is that it muddies the meaning of run IDs.
- **Transcript framing**: if you “retry” a run but reuse the same run ID, then run IDs stop being truly idempotent/unique identifiers of what happened.

### Per-stage run IDs for posts (required by Option 2)

- **Decision** (implied by choosing Option 2): track **per-stage run IDs** for each post:
  - `ingestion_run_id`, `preprocessing_run_id`, `generation_run_id`, `curation_run_id`
- **Why**: a post may be ingested in run 1 but preprocessed in run 2 (or later), so a single “post.run_id” is not sufficient to explain provenance.

### Where metadata lives (and what’s still open)

- **Decision**:
  - **Core artifacts**: S3
  - **Query tables**: Glue + Athena
  - **Run-level metadata**: **DynamoDB** (good fit because low latency + schema-flexible “object storage” for evolving fields)
- **Run metadata schema discussed** (conceptually):
  - `run_id` (PK), `status` (in_progress/succeeded/failed), timestamps, `last_stage`, `message/error`
- **Open question (explicitly unresolved)**: **post-level metadata** write strategy.
  - Writing post metadata only at end of pipeline is “clean” (1 write per post).
  - Writing at each stage multiplies writes (\(\times 4\)); writing at stage start+end multiplies further (\(\times 8\)).
  - DynamoDB is fast but becomes expensive with high write volume; likely eventual answer is **some hybrid of DynamoDB + S3**, but we tabled the final design.

## Scenarios discussed (the concrete correctness tests)

### Scenario A: preprocessing stalls; rerun happens "too soon" (no new posts)

- **Setup**: ingestion succeeded; preprocessing stalls due to transient compute/provisioning issues; a rerun triggers while the most recent ingestion dataset is unchanged.
- **Failure mode**: overlapping runs can both preprocess the same ingested posts and write duplicate outputs (idempotency break).
- **Mitigation chosen**: **dedupe at each node** to reduce duplication and strengthen downstream guarantees, acknowledging remaining race-condition edge cases.

### Scenario B: run 1 ingestion succeeds; preprocessing fails; run 2 ingests new posts

- **Concrete example**:
  - Run 1 ingestion writes posts {1,2,3,4}; preprocessing fails ⇒ posts exist in raw but nowhere else.
  - Run 2 ingestion sees {3,4,5,6,7,8}, filters already-seen {3,4}, writes {5,6,7,8}.
- **Problem** (naive “latest only” preprocessing): preprocessing only processes run 2, leaving {1,2,3,4} **orphaned** forever downstream.
- **Option 1**: manually rerun preprocessing for run 1 after observing failure (Grafana/alerts).
  - **Tradeoff**: requires human ops + creates ambiguity around run IDs / retries.
- **Option 2 (chosen)**: preprocessing processes **all posts not yet preprocessed**, potentially consuming multiple ingestion runs and producing a collapsed/merged output set.
  - **Tradeoff**: more complex provenance tracking, but far less manual remediation.

## Cost/latency tradeoffs explicitly called out

- **S3 vs DynamoDB**:
  - S3: cheap, slower, not ideal for many small writes.
  - DynamoDB: low latency, great for queryable metadata, but expensive at high write volume.
- **Query-time cost at scale**:
  - Avoid full-history scans; prefer bounded “recent window” queries (e.g., last 2 days) for practical idempotency/seen-id computations.
