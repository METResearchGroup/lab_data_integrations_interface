# Step 5. Point the backend at shared S3 and Athena

Make every backend import of `S3` and `Athena` point at `lib.aws`, then delete `backend/agentic_search/aws/`. Leave Glue database and partition column imports on Jetstream constants, because the database name and partition column identify the Bluesky raw tables.

## Scope

- **Caller.** `backend/agentic_search/run_langgraph.py` constructs `Athena()` and `S3()` and passes them into `build_graph`. `execute_query` and graph nodes take the same types as parameters. Tests inject stubs, so they do not import the real classes.
- **Slice.** Change the `Athena` and `S3` import paths in every backend module that currently imports `backend.agentic_search.aws`, delete the backend copies, and confirm query execution and graph tests still pass.
- **Out of scope.** Moving `GLUE_DATABASE` or `PARTITION_SOURCE_COLUMN` out of Jetstream. Changing SQL generation. Changing `data_platform/aws/`. Adding Athena result paging to `lib.aws.athena.Athena`.

## Files to inspect

- `lib/aws/s3.py` and `lib/aws/athena.py` from Step 2
- `backend/agentic_search/aws/s3.py` (to delete)
- `backend/agentic_search/aws/athena.py` (to delete)
- `backend/agentic_search/query_execution/execute.py`
- `backend/agentic_search/graph/graph.py`
- `backend/agentic_search/graph/nodes.py`
- `backend/agentic_search/run_langgraph.py`
- `backend/agentic_search/query_execution/smoke_tests/check_query_execution.py`
- `backend/agentic_search/query_generation/generate.py` (imports `GLUE_DATABASE` and `PARTITION_SOURCE_COLUMN` from Jetstream; leave the Jetstream imports)
- `tests/backend/agentic_search/query_execution/test_execute.py` (uses `StubAthena` and `StubS3`, not the real classes)
- `tests/backend/agentic_search/graph/test_graph.py` (uses `FakeAthena` and `FakeS3`)

## Files allowed to change

- `backend/agentic_search/query_execution/execute.py`
- `backend/agentic_search/graph/graph.py`
- `backend/agentic_search/graph/nodes.py`
- `backend/agentic_search/run_langgraph.py`
- `backend/agentic_search/query_execution/smoke_tests/check_query_execution.py`
- `backend/agentic_search/aws/s3.py` (delete)
- `backend/agentic_search/aws/athena.py` (delete)
- Tests under `tests/backend/agentic_search/` only if an import of the deleted modules exists (today they use stubs and do not import `backend.agentic_search.aws`)

## Files forbidden to change

- `backend/agentic_search/query_generation/generate.py`
- `backend/agentic_search/query_execution/models.py`
- `bluesky_ingestion_jetstream/**`
- `bluesky_backfill_app/**`
- `data_platform/**`
- `lib/aws/**` unless a missing `expires_in` or `run_query` argument blocks the switch (if so, add a `tests/lib/aws/` regression first)

## Contracts

### Import path

In each of the files below, replace `from backend.agentic_search.aws.athena import Athena` and `from backend.agentic_search.aws.s3 import S3` with `from lib.aws.athena import Athena` and `from lib.aws.s3 import S3`.

- `backend/agentic_search/query_execution/execute.py`
- `backend/agentic_search/graph/graph.py`
- `backend/agentic_search/graph/nodes.py`
- `backend/agentic_search/run_langgraph.py`
- `backend/agentic_search/query_execution/smoke_tests/check_query_execution.py`

Keep `from bluesky_ingestion_jetstream.aws.constants import GLUE_DATABASE` in `execute.py`.

Keep `execute_query(generated, *, athena: Athena, s3: S3, expires_in: int = PRESIGNED_URL_TTL_SECONDS)`. The keyword-only `*` on `execute_query` is existing backend style. Do not restyle it in this step.

`athena.run_query(generated.sql, database=GLUE_DATABASE, workgroup=WORKGROUP)` must keep working. Shared `Athena.run_query` takes `query`, `database`, and `workgroup` as required arguments that callers may pass by position or by name (Step 1). Keyword calls from `execute.py` stay valid.

`s3.generate_presigned_url(athena.get_output_location(execution_id), expires_in=expires_in)` must keep working. Shared `S3.generate_presigned_url` requires `expires_in` with no default (Step 1).

`run_langgraph.py` keeps constructing `Athena()` and `S3()` with no arguments. Shared constructors default `region` to `AWS_REGION` and build a client when none is passed (Step 1).

### Deleted package

After no remaining imports, delete:

- `backend/agentic_search/aws/s3.py`
- `backend/agentic_search/aws/athena.py`

If `backend/agentic_search/aws/` is then empty, delete the directory too. Do not leave an empty `__init__.py`.

## Implement-from-spec phases for this step

### Phase 0. Scope

Caller is `run_langgraph` in `backend/agentic_search/run_langgraph.py`, which constructs `Athena()` and `S3()` and passes them into `build_graph`.

### Phase 1. Scaffold

Switch the import paths listed under "Import path". Do not change the body of `execute_query` or `run_langgraph`.

### Phase 2. Contracts

`execute_query` signature and return type stay the same. `WORKGROUP` and `PRESIGNED_URL_TTL_SECONDS` stay in `execute.py`. `run_langgraph` still constructs `Athena()` and `S3()`.

### Phase 3. Test design

`tests/backend/agentic_search/query_execution/test_execute.py` and `tests/backend/agentic_search/graph/test_graph.py` already inject stubs. The query execution and graph tests remain the spec for wiring. Also run `tests/lib/aws/test_s3.py` and `tests/lib/aws/test_athena.py` so the real classes still match Step 1.

### Phase 4. Flesh units of work (order)

1. Retarget imports in the five backend files listed under "Import path".
2. Delete `backend/agentic_search/aws/s3.py` and `backend/agentic_search/aws/athena.py`.
3. Grep for leftover `backend.agentic_search.aws` imports.
4. Run query execution tests, graph tests, and `tests/lib/aws/`.

### Phase 5. Caller complete

Query execution still returns an execution id and a presigned URL. The backend AWS copies are gone.

## Must pass

```bash
uv run pytest tests/backend/agentic_search/query_execution/test_execute.py tests/backend/agentic_search/graph/test_graph.py tests/backend/agentic_search/test_handle_query.py tests/lib/aws/ tests/bluesky_ingestion_jetstream/aws/test_cursor_store.py tests/bluesky_backfill_app/aws/test_did_store.py tests/bluesky_backfill_app/aws/test_queue.py tests/bluesky_backfill_app/gather_users/test_cursor_store.py -q
```

Expected output is exit code 0, all passed.

```bash
uv run python -c "from backend.agentic_search.run_langgraph import run_langgraph; from lib.aws.s3 import S3; from lib.aws.athena import Athena; from backend.agentic_search.graph.graph import build_graph; print(run_langgraph.__name__, S3.__module__, Athena.__module__, build_graph.__module__)"
```

Expected output:

```text
run_langgraph lib.aws.s3 lib.aws.athena backend.agentic_search.graph.graph
```

`test -e backend/agentic_search/aws/s3.py` must fail.

`test -e backend/agentic_search/aws/athena.py` must fail.

`rg -n "backend\\.agentic_search\\.aws|from backend.agentic_search.aws" --glob '*.py'` prints nothing.

## Must fail or must not happen

1. Do not move `GLUE_DATABASE` or `PARTITION_SOURCE_COLUMN` into `lib/aws/`.
2. Do not change `generate.py`.
3. Do not add `upload_file` or Athena row paging in order to "finish" the backend migration.
4. Do not edit `data_platform/aws/`.

Final grep to confirm `data_platform/aws/` is untouched relative to `main` (run from repo root after the step):

```bash
git diff main -- data_platform/aws
```

Expected output is empty.

## Done when

The backend uses `lib.aws.s3.S3` and `lib.aws.athena.Athena`, `backend/agentic_search/aws/` is gone, query execution tests pass, and the Jetstream and backfill migrations from Steps 3 and 4 still pass. The work in `plan.md` is complete.
