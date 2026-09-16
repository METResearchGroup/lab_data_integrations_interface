# Step 1: Confirm candidates, name strings, dates, and output layout

Confirm the candidate table, name strings, query windows, and output columns before any Athena SQL or AWS calls. Scaffold the experiment package so later steps can import constants and stub functions. Tests in this step fail until the constants and schema helpers match the contracts below.

## Scope

- **Caller:** `experiments/democratic_candidate_posts_2026_09_09/main.py` → `run()` (wired in Step 5). Tests in this step are the immediate caller.
- **Task:** Constants, candidate records, output path layout, schema helpers, and failing contract tests.
- **Out of scope:** SQL generation, Athena, S3 download, compile, README, gitignore.

## Files

### Inspect

- `docs/plans/2026-09-09_democratic_candidate_posts_b4c201/plan.md` (confirmed decisions)
- `bluesky_ingestion_jetstream/constants.py` (`DATA_START_DATE = date(2026, 8, 1)`)
- `bluesky_ingestion_jetstream/schemas/arrow_schemas.py` (`POST_SCHEMA` column names `uri`, `did`, `text`, `created_at`)
- `lib/timestamp_utils.py` (`get_current_timestamp()` format `"%Y_%m_%d-%H:%M:%S"`)
- `experiments/aoc_getrepo_derived_stats_2026_08_11/constants.py` (experiment constants layout)
- `experiments/perspective_api_labeling_2026_08_11/download_posts_by_day.py` (export, download, and merge reference for later steps)
- `experiments/reddit_fetch_data_2026_05_23/main.py` (experiment package layout under `experiments/`)

### Allowed to change

- `experiments/democratic_candidate_posts_2026_09_09/__init__.py` (create, empty)
- `experiments/democratic_candidate_posts_2026_09_09/constants.py` (create)
- `experiments/democratic_candidate_posts_2026_09_09/schemas.py` (create)
- `experiments/democratic_candidate_posts_2026_09_09/main.py` (create, thin stub `run()` / `if __name__ == "__main__"` only)
- `tests/experiments/democratic_candidate_posts_2026_09_09/__init__.py` (create, empty)
- `tests/experiments/democratic_candidate_posts_2026_09_09/test_contracts.py` (create)

### Forbidden to change

- `backend/**`
- `bluesky_ingestion_jetstream/**`
- `data_platform/**`
- `ui/**`
- `lib/aws/**`
- `experiments/perspective_api_labeling_2026_08_11/**`
- `pyproject.toml`

## Contracts to confirm

### Coverage floor

Import `DATA_START_DATE` from `bluesky_ingestion_jetstream.constants`. Do not copy the date literal into a second constant. Query start for a candidate is `max(primary_date, DATA_START_DATE)`.

### Candidate table

Exact records, stable order, `candidate_id` values are the only identifiers later SQL and filenames may use:

| `candidate_id` | `display_name` | `primary_date` | `name_strings` (lowercase, match with `LOWER(text) LIKE '%' \|\| string \|\| '%'`) |
|---|---|---|---|
| `el_sayed` | Abdul El-Sayed | 2026-08-04 | `abdul el-sayed`, `el-sayed`, `el sayed`, `elsayed` |
| `talarico` | James Talarico | 2026-03-03 | `james talarico`, `talarico` |
| `becerra` | Xavier Becerra | 2026-06-02 | `xavier becerra`, `xavier beccera` |
| `cooper` | Roy Cooper | 2026-03-03 | `roy cooper` |
| `ossoff` | Jon Ossoff | 2026-05-19 | `jon ossoff`, `jonathan ossoff`, `ossoff` |

Do not add a bare `cooper` or `becerra` string. Do not drop the `xavier beccera` misspelling.

### Query window helper

```python
def query_start_date(primary_date: date) -> date: ...
def query_end_date(run_date: date) -> date: ...
```

- `query_start_date` returns `max(primary_date, DATA_START_DATE)`.
- `query_end_date` returns `run_date` (the UTC calendar date of the run). The SQL in Step 2 treats that date as inclusive by using `created_at < TIMESTAMP '{run_date + 1 day} 00:00:00'`.)

Expected starts given `DATA_START_DATE == 2026-08-01`:

| `candidate_id` | query start |
|---|---|
| `el_sayed` | 2026-08-04 |
| `talarico` | 2026-08-01 |
| `becerra` | 2026-08-01 |
| `cooper` | 2026-08-01 |
| `ossoff` | 2026-08-01 |

### Combined Parquet columns (stable order)

1. `uri` (string)
2. `did` (string)
3. `text` (string)
4. `created_at` (timestamp, no time zone, matching the Athena `CAST(created_at AS TIMESTAMP)` export)
5. `matched_candidate` (string, a `candidate_id` from the table)
6. `matched_name_string` (string, the first `name_strings` entry that matched, in list order)

### Output layout

Under `experiments/democratic_candidate_posts_2026_09_09/data/<run_timestamp>/`:

| Artifact | Purpose |
|---|---|
| `metadata.json` | run timestamp, coverage floor, per-candidate windows, name strings, row counts, match-rule notes |
| `posts.parquet` | combined rows for all candidates |
| `by_candidate/<candidate_id>.parquet` | per-candidate export after S3 merge (Step 3 writes these; schema same as combined plus no extra columns) |

`run_timestamp` comes from `lib.timestamp_utils.get_current_timestamp()`.

### `metadata.json` required keys

- `run_timestamp`
- `glue_database`: `"bluesky_raw"`
- `glue_table`: `"posts"`
- `workgroup`: `"bluesky_raw_maintenance"`
- `coverage_start`: `"2026-08-01"`
- `match_rule`: `"case_insensitive_substring_on_text"`
- `is_criticism_filter`: `false`
- `candidates`: list of objects, one per `candidate_id`, each with `candidate_id`, `display_name`, `primary_date`, `query_start`, `query_end`, `name_strings`, `row_count`

## Implement-from-spec phases for this step

### Phase 0. Scope

Caller = `main.run` (wired in Step 5). File tree:

```text
experiments/democratic_candidate_posts_2026_09_09/
  __init__.py
  constants.py
  schemas.py
  main.py
tests/experiments/democratic_candidate_posts_2026_09_09/
  __init__.py
  test_contracts.py
```

### Phase 1. Scaffold

Create modules so imports resolve. Stub:

- `CANDIDATES` ordered tuple or list of candidate records
- `query_start_date` / `query_end_date` raising `NotImplementedError` until Phase 4
- `COMBINED_COLUMNS` ordered tuple
- `main.run()` raising `NotImplementedError`

### Phase 2. Contracts

Lock `candidate_id` values, `name_strings`, primary dates, column order, and metadata keys to the tables above. Stop if anything contradicts [`../plan.md`](../plan.md).

### Phase 3. Test design (failing)

In `tests/experiments/democratic_candidate_posts_2026_09_09/test_contracts.py`:

1. **Given** the candidates module **when** imported **then** the five `candidate_id` values are exactly `el_sayed`, `talarico`, `becerra`, `cooper`, `ossoff` in that order.
2. **Given** `cooper` **when** name strings are listed **then** the only string is `roy cooper`.
3. **Given** `becerra` **when** name strings are listed **then** they include `xavier becerra` and `xavier beccera` and do not include a bare `becerra`.
4. **Given** `el_sayed` **when** name strings are listed **then** they include `el-sayed`, `el sayed`, and `elsayed`.
5. **Given** each primary date **when** `query_start_date` runs **then** starts match the expected-starts table.
6. **Given** `DATA_START_DATE` **when** imported into the experiment **then** it is the same object/value as `bluesky_ingestion_jetstream.constants.DATA_START_DATE`.
7. **Given** `COMBINED_COLUMNS` **when** listed **then** exact ordered names match the column contract.

### Phase 4 and 5

Implement constants and the two date helpers until contract tests are green. No network. `main.run` may remain `NotImplementedError`.

## Pass / fail

### Must pass before leaving this step

```bash
uv run pytest tests/experiments/democratic_candidate_posts_2026_09_09/test_contracts.py -q
```

Expected: all contract tests pass after helpers are filled; import errors mean scaffold incomplete.

- [ ] Package and contract test file exist at the paths above.
- [ ] Cooper has no surname-only string.
- [ ] Query starts use `DATA_START_DATE` from Jetstream, not a copied literal.
- [ ] No AWS calls in this step's code paths.

### Must fail / must not happen

- [ ] Building Athena SQL in this step.
- [ ] Adding `cooper` or `becerra` as a standalone name string.
- [ ] Copying `date(2026, 8, 1)` into experiment constants instead of importing `DATA_START_DATE`.

## Done when

Candidate identities, name strings, date windows, column order, and metadata keys are locked by tests. Ready for Step 2 SQL against these contracts.
