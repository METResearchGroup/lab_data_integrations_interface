# Step 5: Wire the entrypoint, README, and live smoke checklist

Connect the candidate list, per-candidate export, and compile. Add a README, gitignore the generated `data/` tree, and add a fully mocked end-to-end test. A live Athena smoke is a manual checklist, not a pytest case.

## Scope

- **Caller:** `experiments/democratic_candidate_posts_2026_09_09/main.py` → `run()` and `if __name__ == "__main__"`.
- **Task:** Orchestration, CLI flags, README, gitignore, mocked e2e, live smoke instructions.
- **Out of scope:** Changing the query UI, Jetstream, or `data_platform`. Classifying criticisms.

## Files

### Inspect

- `experiments/democratic_candidate_posts_2026_09_09/export.py`
- `experiments/democratic_candidate_posts_2026_09_09/compile.py`
- `experiments/aoc_getrepo_derived_stats_2026_08_11/main.py` (entrypoint docstring run command)
- `experiments/perspective_api_labeling_2026_08_11/README.md` (operator-facing run instructions)
- `.gitignore` (existing experiment `data/` ignore rules)
- `lib/timestamp_utils.py` (`get_current_timestamp()`)
- `lib/aws/athena.py`
- `backend/agentic_search/query_execution/smoke_tests/check_query_execution.py` (live Athena credentials for `us-east-2`)

### Allowed to change

- `experiments/democratic_candidate_posts_2026_09_09/main.py` (implement `run()`)
- `experiments/democratic_candidate_posts_2026_09_09/README.md` (create)
- `.gitignore` (add `experiments/democratic_candidate_posts_2026_09_09/data/`)
- `tests/experiments/democratic_candidate_posts_2026_09_09/test_main.py` (create)

### Forbidden to change

- `backend/**`
- `bluesky_ingestion_jetstream/**`
- `data_platform/**`
- `ui/**`
- `lib/aws/**` (read-only import of `Athena`)

## Contracts to confirm

### CLI

```bash
PYTHONPATH=. uv run python experiments/democratic_candidate_posts_2026_09_09/main.py
PYTHONPATH=. uv run python experiments/democratic_candidate_posts_2026_09_09/main.py --smoke
PYTHONPATH=. uv run python experiments/democratic_candidate_posts_2026_09_09/main.py --candidate cooper
PYTHONPATH=. uv run python experiments/democratic_candidate_posts_2026_09_09/main.py --smoke --candidate el_sayed
```

| Flag | Meaning |
|---|---|
| (none) | Export all five candidates, no `LIMIT` |
| `--smoke` | Pass `smoke_limit=100` into every `export_candidate` call |
| `--candidate <candidate_id>` | Export only the named id, then compile a combined file that contains only the selected candidate's rows. `metadata.json` `candidates` contains exactly the exported candidates. |

`--candidate` value must be one of the five `candidate_id` values or the process exits with code 2 and a message that lists the valid ids.

### `run()` behavior

1. `run_timestamp = get_current_timestamp()`.
2. `run_date = datetime.now(UTC).date()`.
3. `output_dir = Path("experiments/democratic_candidate_posts_2026_09_09/data") / run_timestamp` (resolve relative to repo root; do not depend on cwd remaining the repo root beyond the documented run command).
4. Select candidates (all, or the one `--candidate`).
5. `athena = Athena()` unless a test injects one.
6. Create a boto3 S3 client for `us-east-2` unless injected.
7. For each selected candidate, `export_candidate(...)`. Print `<candidate_id>: <row_count> rows`.
8. `compile_outputs(...)`.
9. Print the combined path and `total_rows`.

If one candidate export raises, do not compile. Let the exception propagate (no partial `posts.parquet`). Tests pin that compile is not called when the second of two exports raises.

### README must include

- Why the file is a name match, not a criticism sample
- The 2026-08-01 coverage floor, and the fact that four primaries are earlier than 2026-08-01
- The four commands above
- Required AWS credentials for `us-east-2`, Glue database `bluesky_raw`, workgroup `bluesky_raw_maintenance`
- Output paths `data/<run_timestamp>/posts.parquet` and `metadata.json`

## Implement-from-spec phases for this step

### Phase 0. Scope

Caller = `main.run`. Happy path: all five candidates, mocked Athena and S3, files on disk.

### Phase 1. Scaffold

`run()` may still be `NotImplementedError` at the start of this step. Replace it in Phase 4.

### Phase 2. Contracts

CLI flags and metadata-on-subset behavior match the table. No new export SQL.

### Phase 3. Test design (failing)

In `tests/experiments/democratic_candidate_posts_2026_09_09/test_main.py`:

1. **Given** fakes that write five one-row Parquet files **when** `run()` executes with injected Athena and S3 **then** `posts.parquet` exists and `metadata.json` has five candidates whose `row_count` values sum to `total_rows`.
2. **Given** `--candidate cooper` **when** `run()` executes **then** `export_candidate` is called once and metadata `candidates` has one entry with `candidate_id == "cooper"`.
3. **Given** `--smoke` **when** `run()` executes **then** every `export_candidate` call received `smoke_limit=100`.
4. **Given** `--candidate nope` **when** the CLI parses **then** exit code 2.
5. **Given** the second candidate export raising `RuntimeError` **when** `run()` executes **then** `compile_outputs` is not called and no `posts.parquet` is written.

### Phase 4 and 5

Implement `run()` and argparse. Add README and gitignore. Tests green without AWS.

## Pass / fail

### Must pass before leaving this step

```bash
uv run pytest tests/experiments/democratic_candidate_posts_2026_09_09/ -q
uv run ruff check experiments/democratic_candidate_posts_2026_09_09/ tests/experiments/democratic_candidate_posts_2026_09_09/
```

Expected: pytest all green; ruff exits 0.

```bash
rg "experiments/democratic_candidate_posts_2026_09_09/data/" .gitignore
```

Expected: the ignore path is present.

### Live smoke (manual, after unit tests)

Requires AWS credentials that can query `bluesky_raw.posts` in workgroup `bluesky_raw_maintenance`, same as `python -m backend.agentic_search.query_execution.smoke_tests.check_query_execution`.

```bash
PYTHONPATH=. uv run python experiments/democratic_candidate_posts_2026_09_09/main.py --smoke --candidate el_sayed
```

Expected stdout includes `el_sayed:` and a row count. A zero count is allowed if the 100-row smoke export has no name match. `data/<timestamp>/posts.parquet` exists. `metadata.json` has `is_criticism_filter: false` and El-Sayed `query_start` `"2026-08-04"`.

Full five-candidate run is operator work after merge, not a pytest gate:

```bash
PYTHONPATH=. uv run python experiments/democratic_candidate_posts_2026_09_09/main.py
```

### Must fail / must not happen

- [ ] Changing `backend/agentic_search/query_generation/generate.py` to add text `LIKE`.
- [ ] Checking generated Parquet into git.
- [ ] Compiling after a failed export.

## Done when

An implementer can run the mocked tests without AWS, an operator can run `--smoke --candidate el_sayed` against Athena, and the README states the coverage floor and the name-match limit so the Parquet file is not mistaken for a criticism-coded dataset.
