# Step 4: Compile the combined Parquet file and metadata

Concatenate the per-candidate Parquet files into `posts.parquet` and write `metadata.json`. Upload both to the run prefix in S3. Tests mock S3 upload. No Athena.

## Scope

- **Caller:** `experiments/client_request_2026_09_09/main.py` `run()` (Step 5). Immediate caller is `compile_outputs(...)`.
- **Task:** Concatenate rows, preserve per-candidate duplicates, write combined Parquet and metadata locally, upload both to S3.
- **Out of scope:** Athena, CLI, product packages.

## Files

### Inspect

- `experiments/client_request_2026_09_09/schemas.py` (`COMBINED_COLUMNS`, metadata keys from Step 1)
- `experiments/client_request_2026_09_09/constants.py` (candidate table)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/output.py` (timestamped folder plus `metadata.json` write pattern)
- `lib/timestamp_utils.py`

### Allowed to change

- `experiments/client_request_2026_09_09/compile.py` (create)
- `tests/experiments/client_request_2026_09_09/test_compile.py` (create)

### Forbidden to change

- `experiments/client_request_2026_09_09/sql.py`
- `experiments/client_request_2026_09_09/export.py`
- `backend/**`
- `lib/aws/**`

## Contracts to confirm

### `compile_outputs` signature

```python
def compile_outputs(
    run_timestamp: str,
    run_date: date,
    output_dir: Path,
    exports: list[CandidateExportResult],
    s3_client,
) -> CompileResult: ...
```

`CompileResult` fields:

- `posts_path: Path` (`output_dir / "posts.parquet"`)
- `metadata_path: Path` (`output_dir / "metadata.json"`)
- `posts_s3_uri: str`
- `metadata_s3_uri: str`
- `total_rows: int`

### Combined table rules

1. Read each `exports[i].parquet_path` in `CANDIDATES` order (`el_sayed`, `talarico`, `becerra`, `cooper`, `ossoff`). If an export is missing from the list, raise `ValueError` naming the missing `candidate_id`.
2. Concatenate with `pyarrow.concat_tables` (or pandas concat that yields the same columns). Do not drop rows that share a `uri` across candidates.
3. Column order must equal `COMBINED_COLUMNS`.
4. Write `posts.parquet` with `compression="zstd"`.
5. `total_rows` equals the sum of per-candidate `row_count` values and the combined table length.
6. Upload `posts.parquet` to `s3://lab-data-integrations-interface/experiments/client_request_2026_09_09/<run_timestamp>/posts.parquet`.
7. Upload `metadata.json` to `s3://lab-data-integrations-interface/experiments/client_request_2026_09_09/<run_timestamp>/metadata.json`.
8. Do not delete any S3 objects.

### `metadata.json` body

Write UTF-8 JSON with `indent=2` and a trailing newline. Required keys from Step 1. Per-candidate `query_end` is `run_date.isoformat()`. `row_count` comes from `CandidateExportResult`, not from a second file scan, so metadata stays consistent if compile is given explicit counts.

`is_criticism_filter` must be JSON `false`.

Include a `notes` list with exactly these two strings (tests pin the text):

- `"Rows are name matches on post text, not posts labeled as criticisms."`
- `"Query windows start on max(primary_date, 2026-08-01). Jetstream Iceberg coverage of posts begins 2026-08-01."`

## Implement-from-spec phases for this step

### Phase 0. Scope

Caller = `compile_outputs`. Unit of work: local files plus S3 upload of the two compiled objects.

### Phase 1. Scaffold

Create `compile.py` with `compile_outputs` raising `NotImplementedError`.

### Phase 2. Contracts

Signatures and metadata keys match above.

### Phase 3. Test design (failing)

In `tests/experiments/client_request_2026_09_09/test_compile.py`:

1. **Given** five tiny Parquet files, two of which share the same `uri` but different `matched_candidate` **when** compile runs **then** `posts.parquet` has both rows.
2. **Given** the five tiny Parquet files **when** compile runs **then** column order is `uri`, `did`, `text`, `created_at`, `matched_candidate`, `matched_name_string`.
3. **Given** per-candidate row counts 1,0,2,0,1 **when** compile runs **then** `metadata.json` `candidates[].row_count` matches and `total_rows` in the result is 4.
4. **Given** Cooper's export **when** metadata is loaded **then** `query_start` is `"2026-08-01"` and `primary_date` is `"2026-03-03"`.
5. **Given** El-Sayed **when** metadata is loaded **then** `query_start` is `"2026-08-04"`.
6. **Given** the metadata file **when** loaded **then** `is_criticism_filter` is `false` and `notes` contains both pinned strings.
7. **Given** exports missing `ossoff` **when** compile runs **then** `ValueError` mentions `ossoff`.
8. **Given** a fake `s3_client.upload_file` **when** compile runs **then** it uploads `posts.parquet` and `metadata.json` under `experiments/client_request_2026_09_09/<run_timestamp>/`.

### Phase 4 and 5

Implement `compile_outputs` until tests pass.

## Pass / fail

### Must pass before leaving this step

```bash
uv run pytest tests/experiments/client_request_2026_09_09/ -q
```

Expected: all tests in that directory green, including the new compile tests.

### Must fail / must not happen

- [ ] Deduplicating by `uri` across candidates.
- [ ] Calling Athena.
- [ ] Omitting `is_criticism_filter` or the coverage note.
- [ ] Omitting `s3_parquet_uri` on candidate metadata objects.

## Done when

A directory of five per-candidate Parquet files becomes `posts.parquet` plus truthful `metadata.json`. Ready for Step 5 orchestration.
