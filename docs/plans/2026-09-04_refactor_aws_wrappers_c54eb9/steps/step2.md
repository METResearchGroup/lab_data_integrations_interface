# Step 2. Implement the shared clients and bases

Fill in the `lib/aws/` helpers that Step 1 stubbed, until `tests/lib/aws/` passes. Do not change Jetstream, backfill, or the backend yet.

## Scope

- **Caller.** The Step 1 tests under `tests/lib/aws/` are the caller for this step. App classes still import their local copies.
- **Slice.** Real bodies for `error_code`, `build_client` and the service builders, `DynamoDBStore.__init__`, `S3.generate_presigned_url`, `Athena.run_query`, `Athena.get_output_location`, `SqsQueueBase.__init__`, and `SqsQueueBase.send_message_batch`.
- **Out of scope.** Inheritance in app packages, deleting `bluesky_backfill_app/aws/clients.py` or `backend/agentic_search/aws/`, and any Glue or Iceberg work.

## Files to inspect

- `lib/aws/clients.py`, `lib/aws/dynamodb.py`, `lib/aws/s3.py`, `lib/aws/athena.py`, `lib/aws/sqs.py` from Step 1
- `tests/lib/aws/test_clients.py`, `tests/lib/aws/test_dynamodb.py`, `tests/lib/aws/test_s3.py`, `tests/lib/aws/test_athena.py`, `tests/lib/aws/test_sqs.py` from Step 1
- `bluesky_ingestion_jetstream/aws/cursor_store.py` (`error_code`, `build_dynamodb_client`)
- `bluesky_backfill_app/aws/clients.py` (`error_code`, client builders)
- `backend/agentic_search/aws/s3.py` (`generate_presigned_url`)
- `backend/agentic_search/aws/athena.py` (`run_query` poll loop and `get_output_location`)
- `bluesky_backfill_app/aws/queue.py` (`get_queue_url` and `send_message_batch`)

## Files allowed to change

- `lib/aws/clients.py`
- `lib/aws/dynamodb.py`
- `lib/aws/s3.py`
- `lib/aws/athena.py`
- `lib/aws/sqs.py`
- `lib/aws/constants.py` only if a Step 1 constant was left as a placeholder
- `tests/lib/aws/**` only to fix a test that encoded the Step 1 contract incorrectly. Do not weaken assertions.

## Files forbidden to change

- `bluesky_ingestion_jetstream/**`
- `bluesky_backfill_app/**`
- `backend/**`
- `data_platform/**`
- `pyproject.toml`
- `terraform/**`

## Implement-from-spec phases for this step

### Phase 0. Scope

Caller is `uv run pytest tests/lib/aws/ -q`. Out of scope is every app package.

### Phase 1. Scaffold

The tree already exists from Step 1. Do not add new modules.

### Phase 2. Contracts

Keep the Step 1 signatures. If implementation wants a new public name, stop. Put extra behavior in a private helper in the same file instead, and only if a function would otherwise mix client construction with AWS protocol details.

### Phase 3. Test design

Do not add a new test module. If a Step 1 test is missing a FAILED Athena case or a missing-Error `error_code` case, add that case here before implementing, and leave it failing until the body exists.

### Phase 4. Flesh units of work (order)

1. `error_code` and `CONDITIONAL_CHECK_FAILED`.
2. `build_client`, then the four service builders.
3. `DynamoDBStore.__init__` (injected client vs default client).
4. `S3.__init__` and `generate_presigned_url`.
5. `SqsQueueBase.__init__` (explicit URL, resolve from name, `ValueError`) and `send_message_batch`.
6. `Athena.__init__`, `run_query` (success, failed, cancelled), `get_output_location`.

Run `uv run pytest tests/lib/aws/ -q` after each unit. Newly passing tests belong only to the unit just filled in. Tests for later units may still fail until their unit is done.

### Phase 5. Caller complete

All tests in `tests/lib/aws/` pass. App packages still use their local copies.

## Behavior requirements

1. `build_client` must not pass `config=` when `config` is `None`, so backfill keeps today's boto3 defaults.
2. `Athena.run_query` must sleep `POLL_INTERVAL_SECONDS` between polls. Patch `time.sleep` in tests rather than waiting.
3. `S3.generate_presigned_url` must not strip only the first path segment incorrectly. `"s3://bucket/path/key.parquet"` has bucket `bucket` and key `path/key.parquet`.
4. Public functions and classes get numpy-style docstrings. File docstrings state why the module exists. Do not add a `uv run python ...` line on the library modules, because they are not entrypoints.
5. Match existing injection style. Tests pass fake clients in. Production code will omit `client` in later steps.

## Must pass

```bash
uv run pytest tests/lib/aws/ -q
```

Expected output ends with all tests passed (a `passed` count, exit code 0). No `NotImplementedError`.

```bash
uv run ruff check lib/aws tests/lib/aws
```

Expected output:

```text
All checks passed!
```

## Must fail or must not happen

1. No app file is modified.
2. No live AWS call (no real credentials required for this step).
3. No new dependency in `pyproject.toml`. `boto3` and `botocore` are already project dependencies.

## Done when

`tests/lib/aws/` is green against real `lib/aws/` bodies. Ready for Step 3 to point the Jetstream cursor store at `DynamoDBStore`.
