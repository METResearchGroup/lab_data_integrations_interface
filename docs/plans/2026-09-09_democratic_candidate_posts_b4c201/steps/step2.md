# Step 2: Build the per-candidate Athena export SQL

Write a pure function that turns one candidate record plus a run date into an Athena `UNLOAD` statement. Tests pin the SQL text. Do not call Athena or S3.

## Scope

- **Caller:** `experiments/democratic_candidate_posts_2026_09_09/export.py` (Step 3) and unit tests in this step.
- **Task:** `build_unload_sql(candidate, *, run_date, s3_uri, smoke_limit)` returns the export SQL string.
- **Out of scope:** Running the query, S3 download, compile, `main.py` behavior.

## Files

### Inspect

- `docs/plans/2026-09-09_democratic_candidate_posts_b4c201/plan.md`
- `docs/plans/2026-09-09_democratic_candidate_posts_b4c201/steps/step1.md` (candidate records and date helpers)
- `experiments/perspective_api_labeling_2026_08_11/download_posts_by_day.py` (`_build_unload_query`, `UNLOAD` to Parquet with ZSTD, `CAST(created_at AS TIMESTAMP)`)
- `backend/agentic_search/query_generation/generate.py` (date prune on `created_at` with `TIMESTAMP 'YYYY-MM-DD 00:00:00'` and exclusive end = day after `end_date`)
- `bluesky_ingestion_jetstream/aws/constants.py` (`GLUE_DATABASE = "bluesky_raw"`, `PARTITION_SOURCE_COLUMN = "created_at"`)
- `lib/aws/athena.py` (`Athena.run_query(query, database, workgroup)` signature only; do not call it)

### Allowed to change

- `experiments/democratic_candidate_posts_2026_09_09/sql.py` (create)
- `tests/experiments/democratic_candidate_posts_2026_09_09/test_sql.py` (create)

### Forbidden to change

- `experiments/democratic_candidate_posts_2026_09_09/constants.py` (read-only after Step 1)
- `experiments/democratic_candidate_posts_2026_09_09/schemas.py`
- `backend/**`
- `lib/aws/**`
- `experiments/perspective_api_labeling_2026_08_11/**`

## Contracts to confirm

### Function signature

```python
def build_unload_sql(
    candidate: Candidate,
    *,
    run_date: date,
    s3_uri: str,
    smoke_limit: int | None = None,
) -> str: ...
```

`Candidate` is the record type from Step 1 (`candidate_id`, `display_name`, `primary_date`, `name_strings`).

### SQL shape (must match)

Inner select:

- `FROM posts` (database is passed to `Athena.run_query`, not baked into `FROM`)
- Columns:
  - `uri`
  - `did`
  - `text`
  - `CAST(created_at AS TIMESTAMP) AS created_at`
  - `matched_candidate` as a string literal of `candidate.candidate_id`
  - `matched_name_string` as a `CASE` over `name_strings` in list order, first match wins: `WHEN LOWER(text) LIKE '%' || '<escaped>' || '%' THEN '<escaped>'`
- `WHERE created_at >= TIMESTAMP '<query_start> 00:00:00' AND created_at < TIMESTAMP '<query_end + 1 day> 00:00:00'`
- Name predicate: `AND (` joined `OR` of `LOWER(text) LIKE '%' || '<escaped>' || '%' ` for each `name_strings` entry `)`
- If `smoke_limit` is an int, append `LIMIT <smoke_limit>` to the inner select. If `None`, no `LIMIT`.

Outer wrapper, same as `download_posts_by_day.py`:

```sql
UNLOAD (
    <inner select>
)
TO '<s3_uri>'
WITH (format = 'PARQUET', compression = 'ZSTD')
```

Escape a single quote in a name string by doubling it (`'` becomes `''`). Current name strings have no quotes; the test still pins the escaping helper.

Do not filter on `created_at_day`. Do not use `CAST(created_at AS DATE) = DATE '...'`. Do not `ORDER BY` inside `UNLOAD`.

### Athena identifiers (constants, not new env vars)

Reuse from Jetstream / the Perspective script, imported or defined once in `constants.py` if Step 1 did not already add them:

| Name | Value |
|---|---|
| Glue database | `bluesky_raw` |
| Workgroup | `bluesky_raw_maintenance` |
| S3 bucket | `lab-data-integrations-interface` |

Step 2 only interpolates `s3_uri`. Step 3 builds `s3://lab-data-integrations-interface/athena-results/democratic-candidate-posts/<run_timestamp>/<candidate_id>/`.

## Implement-from-spec phases for this step

### Phase 0. Scope

Caller = `build_unload_sql`. One unit of work: SQL string construction.

### Phase 1. Scaffold

Create `sql.py` with `build_unload_sql` raising `NotImplementedError`. Imports resolve from tests.

### Phase 2. Contracts

Signature and SQL clauses match the tables above. Body still a stub until tests exist.

### Phase 3. Test design (failing)

In `tests/experiments/democratic_candidate_posts_2026_09_09/test_sql.py`:

1. **Given** `cooper` and `run_date=date(2026, 9, 9)` **when** SQL is built **then** `WHERE` contains `created_at >= TIMESTAMP '2026-08-01 00:00:00'` and `created_at < TIMESTAMP '2026-09-10 00:00:00'`.
2. **Given** `el_sayed` and the same run date **when** SQL is built **then** start timestamp is `2026-08-04 00:00:00`.
3. **Given** `cooper` **when** SQL is built **then** the name predicate contains `roy cooper` and does not contain a bare `cooper` `LIKE` that would match other Coopers (assert the `LIKE` patterns equal the `name_strings` list wrapped in `%`).
4. **Given** `el_sayed` **when** SQL is built **then** the inner select includes `LIKE` patterns for `el-sayed`, `el sayed`, and `elsayed`.
5. **Given** `becerra` **when** SQL is built **then** patterns include `xavier becerra` and `xavier beccera`.
6. **Given** `smoke_limit=100` **when** SQL is built **then** the inner select contains `LIMIT 100`.
7. **Given** `smoke_limit=None` **when** SQL is built **then** the SQL has no `LIMIT`.
8. **Given** any candidate **when** SQL is built **then** it starts with `UNLOAD`, contains `CAST(created_at AS TIMESTAMP)`, `format = 'PARQUET'`, and `compression = 'ZSTD'`, and uses `FROM posts` not `FROM bluesky_raw.posts`.
9. **Given** `matched_name_string` **when** SQL is built **then** a `CASE` / `WHEN LOWER(text) LIKE` chain lists `name_strings` in contract order.

### Phase 4 and 5

Implement `build_unload_sql` until the tests in this step pass. No boto3.

## Pass / fail

### Must pass before leaving this step

```bash
uv run pytest tests/experiments/democratic_candidate_posts_2026_09_09/test_sql.py tests/experiments/democratic_candidate_posts_2026_09_09/test_contracts.py -q
```

Expected: all green.

### Must fail / must not happen

- [ ] Calling `Athena.run_query` from `sql.py`.
- [ ] Filtering on `created_at_day`.
- [ ] Putting the Glue database name in the `FROM` clause.

## Done when

`build_unload_sql` is fully specified by tests. Step 3 can pass the returned string to Athena unchanged.
