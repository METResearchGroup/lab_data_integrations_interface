# Step 3. Point Jetstream's cursor store at the DynamoDB base

Make `DynamoCursorStore` inherit from `lib.aws.dynamodb.DynamoDBStore`, and use the shared error helper and client builder. Keep the cursor read and write behavior unchanged. Leave Glue, Iceberg, retry, and dead-letter modules in `bluesky_ingestion_jetstream/aws/`.

## Scope

- **Caller.** `bluesky_ingestion_jetstream/main.py` constructs `DynamoCursorStore` and calls `read` / `write`. The import path stays `bluesky_ingestion_jetstream.aws.cursor_store.DynamoCursorStore`.
- **Slice.** Inheritance and shared imports on the resume cursor store, plus moving `AWS_REGION` so Jetstream constants import it from `lib.aws.constants` instead of defining a second copy.
- **Out of scope.** Backfill, backend, `data_platform/aws/`, Iceberg append, Glue catalog, commit retry, dead-letter writes, and changing the rule that refuses to move the cursor backwards.

## Files to inspect

- `lib/aws/dynamodb.py` and `lib/aws/clients.py` from Step 2
- `bluesky_ingestion_jetstream/aws/cursor_store.py` (current `DynamoCursorStore`, `error_code`, `build_dynamodb_client`, `CONDITIONAL_CHECK_FAILED`)
- `bluesky_ingestion_jetstream/aws/constants.py` (`AWS_REGION`, `DYNAMODB_MAX_ATTEMPTS`, `DYNAMODB_CONNECT_TIMEOUT_SECONDS`, `DYNAMODB_READ_TIMEOUT_SECONDS`, cursor table names)
- `bluesky_ingestion_jetstream/aws/catalog.py` and `bluesky_ingestion_jetstream/aws/dead_letter.py` (they import `AWS_REGION` from Jetstream constants)
- `bluesky_ingestion_jetstream/main.py` (constructs `DynamoCursorStore()` with no client)
- `tests/bluesky_ingestion_jetstream/aws/test_cursor_store.py`

## Files allowed to change

- `bluesky_ingestion_jetstream/aws/cursor_store.py`
- `bluesky_ingestion_jetstream/aws/constants.py` (replace the local `AWS_REGION = "us-east-2"` assignment with `from lib.aws.constants import AWS_REGION`, so `TABLE_LOCATIONS` and `DEAD_LETTER_ROOT` still build from the same name)
- `tests/bluesky_ingestion_jetstream/aws/test_cursor_store.py` only if an import of a moved helper breaks. Do not change assertions.

## Files forbidden to change

- `bluesky_ingestion_jetstream/aws/bootstrap.py`
- `bluesky_ingestion_jetstream/aws/catalog.py` (it may keep importing `AWS_REGION` from `bluesky_ingestion_jetstream.aws.constants`, which still re-exports it)
- `bluesky_ingestion_jetstream/aws/iceberg_writer.py`
- `bluesky_ingestion_jetstream/aws/retry.py`
- `bluesky_ingestion_jetstream/aws/dead_letter.py`
- `bluesky_backfill_app/**`
- `backend/**`
- `data_platform/**`
- `lib/aws/**` unless a Step 2 bug blocks inheritance (if so, add a regression test in `tests/lib/aws/` first)

`catalog.py` and `dead_letter.py` are forbidden even though they import `AWS_REGION`, because `constants.py` will still export that name. Do not retarget `catalog.py` or `dead_letter.py` to `lib.aws.constants` in this step.

## Contracts

### `DynamoCursorStore`

- `class DynamoCursorStore(DynamoDBStore):`
- Public methods `read` and `write` stay on this subclass with the same signatures and behavior as today.
- `__init__(self, client=None, table: str = CURSOR_TABLE, stream_id: str = CURSOR_STREAM_ID)` keeps that argument order so `DynamoCursorStore(client=fake)` in tests still works.
- Call `super().__init__(table=table, client=client, region=AWS_REGION, config=config)` where `config` is a `botocore.config.Config` with `retries={"max_attempts": DYNAMODB_MAX_ATTEMPTS, "mode": "standard"}`, `connect_timeout=DYNAMODB_CONNECT_TIMEOUT_SECONDS`, and `read_timeout=DYNAMODB_READ_TIMEOUT_SECONDS`.
- When a test passes `client=`, `DynamoDBStore` must not call boto3 (Step 1 contract). The `Config` object is only used when `client` is `None`.
- Delete local `error_code`, `build_dynamodb_client`, and `CONDITIONAL_CHECK_FAILED` from `cursor_store.py`. Import `error_code` and `CONDITIONAL_CHECK_FAILED` from `lib.aws.clients`.
- `write` still treats `ConditionalCheckFailedException` as a warning, not a raise. Other `ClientError`s still raise.

### `AWS_REGION` in Jetstream constants

- `bluesky_ingestion_jetstream/aws/constants.py` must not assign `AWS_REGION = "us-east-2"`.
- It must import `AWS_REGION` from `lib.aws.constants`.
- `TABLE_LOCATIONS` and `DEAD_LETTER_ROOT` keep using `AWS_REGION` / `S3_BUCKET` as they do today.
- Cursor table names stay in this file.

## Implement-from-spec phases for this step

### Phase 0. Scope

Caller is `bluesky_ingestion_jetstream/main.py` and `tests/bluesky_ingestion_jetstream/aws/test_cursor_store.py`.

### Phase 1. Scaffold

Change the class line to inherit `DynamoDBStore` and wire `super().__init__` before editing `read` / `write`. Leave `read` / `write` bodies in place.

### Phase 2. Contracts

Confirm `read` and `write` signatures are unchanged. Confirm `main.py` still imports `DynamoCursorStore` from `bluesky_ingestion_jetstream.aws.cursor_store`.

### Phase 3. Test design

Do not rewrite `test_cursor_store.py`. The existing tests are the spec for cursor behavior. Run them before changing production code if you need a baseline, then again after.

### Phase 4. Flesh units of work (order)

1. Import `AWS_REGION` from `lib.aws.constants` in `bluesky_ingestion_jetstream/aws/constants.py`.
2. Switch `DynamoCursorStore` to inherit and delete the local client and error helpers.
3. Run the cursor store tests.

### Phase 5. Caller complete

`main.py` still constructs `DynamoCursorStore()`. Cursor tests pass. Iceberg modules are untouched.

## Must pass

```bash
uv run pytest tests/bluesky_ingestion_jetstream/aws/test_cursor_store.py tests/lib/aws/ -q
```

Expected output is exit code 0, all passed.

```bash
uv run python -c "from bluesky_ingestion_jetstream.aws.cursor_store import DynamoCursorStore; from lib.aws.dynamodb import DynamoDBStore; assert issubclass(DynamoCursorStore, DynamoDBStore); print('ok')"
```

Expected output:

```text
ok
```

```bash
uv run python -c "from bluesky_ingestion_jetstream.aws.constants import AWS_REGION; from lib.aws.constants import AWS_REGION as SHARED; assert AWS_REGION is SHARED; print(AWS_REGION)"
```

Expected output:

```text
us-east-2
```

`rg -n "def build_dynamodb_client|def error_code|CONDITIONAL_CHECK_FAILED" bluesky_ingestion_jetstream/aws/cursor_store.py` prints nothing.

## Must fail or must not happen

1. `read` does not start treating a missing item as a live cursor, and `write` does not start raising on `ConditionalCheckFailedException`.
2. No edits to `bootstrap.py`, `catalog.py`, `iceberg_writer.py`, `retry.py`, or `dead_letter.py`.
3. No new DynamoDB table or Terraform resource.
4. `tests/bluesky_ingestion_jetstream/aws/test_constants.py` still passes, because `PARTITION_SOURCE_COLUMN` and `TABLE_PROPERTIES` stayed in Jetstream constants.

```bash
uv run pytest tests/bluesky_ingestion_jetstream/aws/test_constants.py -q
```

Expected output is exit code 0.

## Done when

`DynamoCursorStore` is a `DynamoDBStore` subclass, Jetstream no longer defines its own region string, and cursor tests still describe the same resume behavior. Ready for Step 4 to migrate backfill.
