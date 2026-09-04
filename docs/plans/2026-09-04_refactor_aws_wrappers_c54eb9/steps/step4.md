# Step 4. Point backfill stores and queue at the shared bases

Make the backfill DID store and listRepos cursor store inherit from `DynamoDBStore`. Make the DID queue inherit from `SqsQueueBase`. Delete `bluesky_backfill_app/aws/clients.py` after its callers import from `lib.aws.clients`. Keep DID status rules and DID message bodies in the backfill package.

## Scope

- **Caller.** `bluesky_backfill_app/gather_users/discovery/main.py` and `enqueue/main.py` construct `DynamoDidStore` and `SqsQueue`. `bluesky_backfill_app/gather_users/cursor_store.py` is constructed from discovery. `bluesky_backfill_app/smoke.py` calls `build_dynamodb_client`. The construction sites stay in the backfill package.
- **Slice.** Inheritance on the three classes, shared client imports, deletion of `clients.py`, and removal of the unused `AWS_REGION` assignment in `bluesky_backfill_app/aws/constants.py`.
- **Out of scope.** Jetstream Iceberg modules, backend S3 and Athena, `data_platform/aws/`, changing shard math, status values, or SQS message JSON.

## Files to inspect

- `lib/aws/dynamodb.py`, `lib/aws/sqs.py`, `lib/aws/clients.py`, `lib/aws/constants.py`
- `bluesky_backfill_app/aws/clients.py` (to delete)
- `bluesky_backfill_app/aws/did_store.py`
- `bluesky_backfill_app/aws/queue.py`
- `bluesky_backfill_app/aws/constants.py`
- `bluesky_backfill_app/gather_users/cursor_store.py`
- `bluesky_backfill_app/smoke.py`
- `tests/bluesky_backfill_app/aws/test_did_store.py`
- `tests/bluesky_backfill_app/aws/test_queue.py`
- `tests/bluesky_backfill_app/gather_users/test_cursor_store.py`

## Files allowed to change

- `bluesky_backfill_app/aws/did_store.py`
- `bluesky_backfill_app/aws/queue.py`
- `bluesky_backfill_app/aws/clients.py` (delete the file)
- `bluesky_backfill_app/aws/constants.py` (remove `AWS_REGION`; nothing else in this file should change)
- `bluesky_backfill_app/gather_users/cursor_store.py`
- `bluesky_backfill_app/smoke.py`
- `tests/bluesky_backfill_app/aws/test_did_store.py` only for broken imports
- `tests/bluesky_backfill_app/aws/test_queue.py` only for broken imports (`SQS_BATCH_SIZE` and `chunked` may stay imported from `bluesky_backfill_app.aws.queue`)
- `tests/bluesky_backfill_app/gather_users/test_cursor_store.py` only for broken imports

## Files forbidden to change

- `bluesky_ingestion_jetstream/**`
- `backend/**`
- `data_platform/**`
- `bluesky_backfill_app/gather_users/discovery/main.py` (it already imports `DynamoDidStore` from `did_store.py`; keep that path)
- `bluesky_backfill_app/gather_users/enqueue/main.py` (it already imports `DynamoDidStore` and `SqsQueue`; keep those paths)
- DID table name, queue name, and status constants in `bluesky_backfill_app/aws/constants.py` other than deleting `AWS_REGION`
- `lib/aws/**` unless a Step 2 bug blocks inheritance

## Contracts

### `DynamoDidStore`

- `class DynamoDidStore(DynamoDBStore):`
- Keep `__init__(self, client=None, table: str = DID_TABLE, concurrency: int = WRITE_CONCURRENCY)`.
- Call `super().__init__(table=table, client=client, region=AWS_REGION, config=None)` so the default client has no botocore `Config`, matching today's `build_dynamodb_client` in `clients.py`.
- Import `AWS_REGION` from `lib.aws.constants`.
- Import `error_code` and `CONDITIONAL_CHECK_FAILED` from `lib.aws.clients`.
- Keep `put_new`, `write`, `set_status`, `set_status_many`, `query_by_status`, `shard_key`, and `status_shard` on this module with current behavior.

### `DynamoCursorStore` in `gather_users/cursor_store.py`

- `class DynamoCursorStore(DynamoDBStore):`
- Keep `__init__(self, client=None, table: str = CURSOR_TABLE, run_id: str = CURSOR_RUN_ID)`.
- Call `super().__init__(table=table, client=client, region=AWS_REGION, config=None)`.
- Keep `read` and `write` bodies. Do not copy Jetstream's monotonic condition onto this store.

### `SqsQueue`

- In `bluesky_backfill_app/aws/queue.py`, `from lib.aws.sqs import SQS_BATCH_SIZE, SqsQueueBase`.
- `class SqsQueue(SqsQueueBase):`
- Keep `__init__(self, client=None, queue_url: str | None = None, queue_name: str = QUEUE_NAME)` and pass those values to `super().__init__(client=client, queue_url=queue_url, queue_name=queue_name, region=AWS_REGION)`.
- Keep `message_body`, `chunked`, `send_batch`, and `send` on the subclass.
- `send_batch` must call `self.send_message_batch(entries)` (the base method) instead of `self.client.send_message_batch(...)`.
- Re-export `SQS_BATCH_SIZE` from this module so `tests/bluesky_backfill_app/aws/test_queue.py` can keep importing it from `bluesky_backfill_app.aws.queue`.

### `clients.py` deletion

- After `did_store.py`, `queue.py`, `gather_users/cursor_store.py`, and `smoke.py` import builders from `lib.aws.clients`, delete `bluesky_backfill_app/aws/clients.py`.
- `smoke.py` currently does `client = build_dynamodb_client()`. Change it to `build_dynamodb_client(AWS_REGION, None)`.

### `constants.py`

- Delete `AWS_REGION = "us-east-2"` from `bluesky_backfill_app/aws/constants.py`.
- Leave `DID_TABLE`, `QUEUE_NAME`, status strings, and shard settings in place.

## Implement-from-spec phases for this step

### Phase 0. Scope

Callers are discovery, enqueue, smoke, and the three test modules listed above.

### Phase 1. Scaffold

Switch class lines to inherit and wire `super().__init__` first. Leave DID and SQS method bodies in place.

### Phase 2. Contracts

`DynamoDidStore`, `SqsQueue`, and gather_users `DynamoCursorStore` keep their public method names. Import paths used by discovery and enqueue do not change.

### Phase 3. Test design

Existing tests are the spec. Do not convert them into tests of `DynamoDBStore` itself.

### Phase 4. Flesh units of work (order)

1. `DynamoDidStore` inheritance and shared error imports. Run `test_did_store.py`.
2. gather_users `DynamoCursorStore` inheritance. Run `test_cursor_store.py`.
3. `SqsQueue` inheritance and `send_batch` using the base method. Run `test_queue.py`.
4. Update `smoke.py`, delete `clients.py`, delete `AWS_REGION` from backfill constants.
5. Grep for leftover `bluesky_backfill_app.aws.clients` imports.

### Phase 5. Caller complete

Discovery, enqueue, and smoke import the same backfill class names as before. `clients.py` is gone.

## Must pass

```bash
uv run pytest tests/bluesky_backfill_app/aws/test_did_store.py tests/bluesky_backfill_app/aws/test_queue.py tests/bluesky_backfill_app/gather_users/test_cursor_store.py tests/lib/aws/ -q
```

Expected output is exit code 0, all passed.

```bash
uv run python -c "from bluesky_backfill_app.aws.did_store import DynamoDidStore; from bluesky_backfill_app.aws.queue import SqsQueue; from bluesky_backfill_app.gather_users.cursor_store import DynamoCursorStore; from lib.aws.dynamodb import DynamoDBStore; from lib.aws.sqs import SqsQueueBase; assert issubclass(DynamoDidStore, DynamoDBStore); assert issubclass(DynamoCursorStore, DynamoDBStore); assert issubclass(SqsQueue, SqsQueueBase); print('ok')"
```

Expected output:

```text
ok
```

`test -e bluesky_backfill_app/aws/clients.py` must fail (file absent).

`rg -n "bluesky_backfill_app\\.aws\\.clients|from bluesky_backfill_app.aws.clients" --glob '*.py'` prints nothing.

## Must fail or must not happen

1. `put_new` still returns `False` on `ConditionalCheckFailedException` and still raises on other `ClientError`s.
2. `SqsQueue.send` still returns failed DIDs and still chunks at 10.
3. gather_users `DynamoCursorStore.write` still `ADD`s the discovered count. Do not add Jetstream's "cursor cannot move backwards" condition.
4. Do not recreate `clients.py` as a re-export module.

## Done when

Backfill's DynamoDB stores and SQS queue inherit from `lib/aws/`, `clients.py` is gone, and the existing backfill AWS tests still pass. Ready for Step 5 to migrate the backend.
