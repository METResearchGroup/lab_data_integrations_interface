# Step 3: Export, download, and write one Parquet file per candidate

Run one candidate's `UNLOAD` through Athena, download the Parquet parts from S3, merge them into `by_candidate/<candidate_id>.parquet`, and delete the temporary S3 prefix. Tests mock Athena and S3. Do not compile the five files yet.

## Scope

- **Caller:** `experiments/democratic_candidate_posts_2026_09_09/main.py` → `run()` (Step 5). Immediate caller for TDD is `export_candidate(...)`.
- **Task:** For one candidate, build SQL (Step 2), run it, download, merge, cleanup, return local path and row count.
- **Out of scope:** Combined `posts.parquet`, `metadata.json`, CLI flags, product packages.

## Files

### Inspect

- `experiments/perspective_api_labeling_2026_08_11/download_posts_by_day.py` (`_delete_s3_prefix`, `_download_s3_prefix`, `_merge_parquet_files`, and `download_day` control flow)
- `lib/aws/athena.py` (`Athena.run_query(self, query: str, database: str, workgroup: str) -> str`)
- `lib/aws/s3.py` (presign only; do not add methods here)
- `lib/aws/constants.py` (`AWS_REGION = "us-east-2"`)
- `bluesky_ingestion_jetstream/aws/constants.py` (`S3_BUCKET = "lab-data-integrations-interface"`, `GLUE_DATABASE = "bluesky_raw"`)
- `experiments/democratic_candidate_posts_2026_09_09/sql.py` (`build_unload_sql`)
- `experiments/democratic_candidate_posts_2026_09_09/constants.py`

### Allowed to change

- `experiments/democratic_candidate_posts_2026_09_09/s3_export.py` (create; copy the three S3 helpers from `download_posts_by_day.py`, do not import from that experiment)
- `experiments/democratic_candidate_posts_2026_09_09/export.py` (create)
- `experiments/democratic_candidate_posts_2026_09_09/constants.py` (add `S3_BUCKET`, `GLUE_DATABASE`, `WORKGROUP`, `S3_EXPORT_ROOT = "athena-results/democratic-candidate-posts"` only if they were not added in Step 1)
- `tests/experiments/democratic_candidate_posts_2026_09_09/test_export.py` (create)

### Forbidden to change

- `lib/aws/s3.py`
- `lib/aws/athena.py`
- `experiments/perspective_api_labeling_2026_08_11/download_posts_by_day.py`
- `backend/**`
- `data_platform/**`

## Contracts to confirm

### S3 prefix

```text
s3://lab-data-integrations-interface/athena-results/democratic-candidate-posts/<run_timestamp>/<candidate_id>/
```

`s3_uri` passed to `build_unload_sql` must include the trailing slash.

### `export_candidate` signature

```python
def export_candidate(
    candidate: Candidate,
    *,
    run_date: date,
    run_timestamp: str,
    output_dir: Path,
    athena: Athena,
    s3_client,
    smoke_limit: int | None = None,
) -> CandidateExportResult: ...
```

`CandidateExportResult` fields:

- `candidate_id: str`
- `parquet_path: Path` (`output_dir / "by_candidate" / f"{candidate_id}.parquet"`)
- `row_count: int`

### Behavior (dependency order)

1. Compute `s3_prefix` and `s3_uri`.
2. Delete any leftover objects under that prefix (same paginated `delete_objects` loop as `download_posts_by_day.py`).
3. `sql = build_unload_sql(...)`.
4. `athena.run_query(sql, database=GLUE_DATABASE, workgroup=WORKGROUP)`.
5. Download all non-folder keys under the prefix into a temporary directory.
6. If `run_query` succeeded and zero files were downloaded, write an empty Parquet file with the combined-column schema from Step 1, set `row_count` to `0`, and continue cleanup. A successful query with no matches is not an error.
7. If files were downloaded, merge parts with `pyarrow.parquet` into `parquet_path` using `compression="zstd"`. If the merged table has zero rows, still write the empty file and return `row_count == 0`.
8. Delete the S3 prefix again.
9. Return `CandidateExportResult` with `row_count` equal to the merged table's number of rows (zero when empty).

`run_query` raising `RuntimeError` (Athena `FAILED` or `CANCELLED`) still fails the candidate. Do not catch that error and pretend the result was empty.

### AWS wiring

- Construct `Athena()` the same way `backend/agentic_search/query_execution/execute.py` does (default client). Tests inject a fake `athena` with `run_query`.
- `s3_client` is a boto3 S3 client for `us-east-2`. Tests inject a fake with `get_paginator` / `download_file` / `delete_objects`.

## Implement-from-spec phases for this step

### Phase 0. Scope

Caller = `export_candidate`. Unit of work: one candidate export path.

### Phase 1. Scaffold

Create `s3_export.py` and `export.py` with stubs. Imports resolve.

### Phase 2. Contracts

Signatures and `CandidateExportResult` fields match above. Bodies `NotImplementedError`.

### Phase 3. Test design (failing)

In `tests/experiments/democratic_candidate_posts_2026_09_09/test_export.py`:

1. **Given** a fake Athena whose `run_query` records the SQL, and a fake S3 that serves one Parquet part with one row **when** `export_candidate` runs **then** `run_query` is called once with `database="bluesky_raw"` and `workgroup="bluesky_raw_maintenance"`, and the local file exists with `row_count == 1`.
2. **Given** the Cooper happy path **when** SQL is inspected **then** `TO` contains `athena-results/democratic-candidate-posts/<run_timestamp>/cooper/`.
3. **Given** a successful query and S3 listing zero keys **when** `export_candidate` runs **then** it writes an empty Parquet at the expected path and returns `row_count == 0` (does not raise).
4. **Given** `smoke_limit=100` **when** `export_candidate` runs **then** the SQL passed to `run_query` contains `LIMIT 100`.
5. **Given** the Cooper export with one downloaded part **when** finished **then** the fake S3 delete helper was used (prefix cleared after download).

Use a real tiny Parquet written to a temp path as the object `download_file` copies. Do not hit AWS.

### Phase 4 and 5

Implement `s3_export.py` helpers first, then `export_candidate`, until the tests pass.

## Pass / fail

### Must pass before leaving this step

```bash
uv run pytest tests/experiments/democratic_candidate_posts_2026_09_09/ -q
```

Expected: Step 1 and Step 2 tests still pass; new export tests pass; no network.

### Must fail / must not happen

- [ ] Editing `lib/aws/s3.py`.
- [ ] Importing helpers from `experiments/perspective_api_labeling_2026_08_11/`.
- [ ] Writing `posts.parquet` or `metadata.json` in this step.

## Done when

One candidate can be exported to a local Parquet file behind mocked Athena and S3. Ready for Step 4 compile.
