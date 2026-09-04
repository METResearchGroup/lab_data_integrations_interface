# Step 1. Scaffold the shared package and freeze contracts

Create `lib/aws/` and freeze the public signatures for client construction, the error helper, and the DynamoDB, S3, Athena, and SQS helpers. Write failing tests that encode the contracts. Do not implement AWS calls yet, and do not change Jetstream, backfill, or the backend.

## Scope

- **Caller.** Later steps will import from `lib/aws/` in `bluesky_ingestion_jetstream/aws/cursor_store.py`, `bluesky_backfill_app/aws/did_store.py`, `bluesky_backfill_app/aws/queue.py`, `bluesky_backfill_app/gather_users/cursor_store.py`, `backend/agentic_search/run_langgraph.py`, `backend/agentic_search/graph/graph.py`, `backend/agentic_search/graph/nodes.py`, `backend/agentic_search/query_execution/execute.py`, and `backend/agentic_search/query_execution/smoke_tests/check_query_execution.py`. The listed callers stay untouched in this step.
- **Slice.** Package marker, frozen signatures, and failing contract tests only.
- **Out of scope.** Filling in boto3 calls, inheriting from the new bases, deleting app copies, Glue, Iceberg, dead-letter code, and `data_platform/aws/`.

## Files to inspect

- `lib/timestamp_utils.py` and `lib/load_env_vars.py` for how shared `lib/` modules are laid out and documented
- `lib/constants.py` for the style of the existing shared constants
- `bluesky_ingestion_jetstream/aws/cursor_store.py` for `error_code`, `CONDITIONAL_CHECK_FAILED`, `build_dynamodb_client`, and `DynamoCursorStore.__init__`
- `bluesky_backfill_app/aws/clients.py` for the backfill copies of `error_code`, `CONDITIONAL_CHECK_FAILED`, `build_dynamodb_client`, and `build_sqs_client`
- `bluesky_backfill_app/aws/queue.py` for SQS construction, `SQS_BATCH_SIZE`, and `send_message_batch`
- `backend/agentic_search/aws/s3.py` for `S3.generate_presigned_url`
- `backend/agentic_search/aws/athena.py` for `Athena.run_query`, `Athena.get_output_location`, and `POLL_INTERVAL_SECONDS`
- `data_platform/aws/s3.py` and `data_platform/aws/athena.py` only to confirm they are out of scope (do not copy `upload_file`, `fetch_rows`, or partition registration)
- `tests/bluesky_ingestion_jetstream/aws/test_cursor_store.py` for FakeClient injection
- `.cursor/skills/implement-plan-and-open-pr/UNIT_TESTING_STANDARDS.md` for test class layout
- `.cursor/skills/write-docstring/SKILL.md` for numpy-style docstrings on new public functions and classes

## Files allowed to change

- `lib/aws/__init__.py` (create, empty package marker)
- `lib/aws/constants.py` (create)
- `lib/aws/clients.py` (create)
- `lib/aws/dynamodb.py` (create)
- `lib/aws/s3.py` (create)
- `lib/aws/athena.py` (create)
- `lib/aws/sqs.py` (create)
- `tests/lib/aws/test_clients.py` (create)
- `tests/lib/aws/test_dynamodb.py` (create)
- `tests/lib/aws/test_s3.py` (create)
- `tests/lib/aws/test_athena.py` (create)
- `tests/lib/aws/test_sqs.py` (create)

## Files forbidden to change

- `bluesky_ingestion_jetstream/**`
- `bluesky_backfill_app/**`
- `backend/**`
- `data_platform/**`
- `pyproject.toml`
- `terraform/**`
- Any existing file under `tests/` except the new `tests/lib/aws/` files listed above

## Contracts to freeze

### `lib/aws/constants.py`

- `AWS_REGION = "us-east-2"`
- Jetstream, backfill, and the backend all use this region today. Do not add Glue database names, table names, bucket names, or queue names here.

### `lib/aws/clients.py`

- `CONDITIONAL_CHECK_FAILED = "ConditionalCheckFailedException"`
- `error_code(error: ClientError) -> str` returns `error.response.get("Error", {}).get("Code", "")`. Match `bluesky_backfill_app/aws/clients.py` and `bluesky_ingestion_jetstream/aws/cursor_store.py`.
- `build_client(service_name: str, region: str, config: Config | None)` calls `boto3.client(service_name, region_name=region)` when `config` is `None`, and passes `config=config` when it is not `None`.
- `build_dynamodb_client(region: str, config: Config | None)` calls `build_client("dynamodb", region, config)`.
- `build_sqs_client(region: str, config: Config | None)` calls `build_client("sqs", region, config)`.
- `build_s3_client(region: str, config: Config | None)` calls `build_client("s3", region, config)`.
- `build_athena_client(region: str, config: Config | None)` calls `build_client("athena", region, config)`.
- Do not give `region` a default. Callers pass `AWS_REGION`.
- Do not add a Glue client builder. Glue stays in `bluesky_ingestion_jetstream/aws/catalog.py`.

### `lib/aws/dynamodb.py`

- Class name `DynamoDBStore`.
- `__init__(self, table: str, client=None, region: str = AWS_REGION, config: Config | None = None) -> None`
- When `client` is not `None`, store it on `self.client` and do not call boto3.
- When `client` is `None`, set `self.client` from `build_dynamodb_client(region, config)`.
- Store `table` on `self.table`.
- Do not add `get_item`, `put_item`, `update_item`, or `query` helpers on the base. Subclasses will keep calling `self.client` the way they do today.

### `lib/aws/s3.py`

- Class name `S3`.
- `__init__(self, region: str = AWS_REGION, client=None) -> None` stores an injected `client`, or `build_s3_client(region, None)`.
- `generate_presigned_url(self, s3_uri: str, expires_in: int) -> str` splits `s3://bucket/key` the way `backend/agentic_search/aws/s3.py` does. Strip the `s3://` prefix, then `partition("/")` so the bucket is the first segment and the key is the rest. Call `self.client.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in)` and return that string.
- `expires_in` is required. Do not default it to 86400. `backend/agentic_search/query_execution/execute.py` already passes `PRESIGNED_URL_TTL_SECONDS`.
- Do not add `upload_file`. `upload_file` exists only on `data_platform/aws/s3.py`, which is out of scope.

### `lib/aws/athena.py`

- `POLL_INTERVAL_SECONDS = 1.0` (same value as `backend/agentic_search/aws/athena.py`).
- Class name `Athena`.
- `__init__(self, region: str = AWS_REGION, client=None) -> None` stores an injected `client`, or `build_athena_client(region, None)`.
- `run_query(self, query: str, database: str, workgroup: str) -> str` submits with `start_query_execution`, then polls `get_query_execution` until `SUCCEEDED`. Sleep `POLL_INTERVAL_SECONDS` between polls. Return the execution id. On `FAILED` or `CANCELLED`, raise `RuntimeError` whose message includes the state and `StateChangeReason` (fallback `"unknown"`), matching `backend/agentic_search/aws/athena.py`.
- `database` and `workgroup` are required. Do not default them to `data_platform` workgroup names.
- `get_output_location(self, execution_id: str) -> str` returns `QueryExecution.ResultConfiguration.OutputLocation`.
- Do not add `fetch_column_as_set`, `fetch_rows`, `query_column_as_set`, or `register_partition`.

### `lib/aws/sqs.py`

- `SQS_BATCH_SIZE = 10` (the AWS `SendMessageBatch` limit, currently in `bluesky_backfill_app/aws/queue.py`).
- Class name `SqsQueueBase`.
- `__init__(self, client=None, queue_url: str | None = None, queue_name: str | None = None, region: str = AWS_REGION) -> None`
- When `client` is not `None`, store it. When `client` is `None`, set it from `build_sqs_client(region, None)`.
- When `queue_url` is not `None`, store it on `self.queue_url`.
- When `queue_url` is `None`, resolve `self.queue_url` from `self.client.get_queue_url(QueueName=queue_name)["QueueUrl"]`.
- If both `queue_url` and `queue_name` are `None`, raise `ValueError`.
- `send_message_batch(self, entries: list[dict]) -> dict` returns `self.client.send_message_batch(QueueUrl=self.queue_url, Entries=entries)`.
- Do not add DID `message_body` or `send(dids, run_id)`. DID message helpers stay on the backfill subclass in Step 4.

## Implement-from-spec phases for this step

### Phase 0. Scope

Caller for later steps is the app classes named above. File tree is the `lib/aws/` and `tests/lib/aws/` paths in "Files allowed to change".

### Phase 1. Scaffold

Create the modules so `from lib.aws.clients import error_code` and the other public names import. Function and method bodies may raise `NotImplementedError`, except `AWS_REGION`, `CONDITIONAL_CHECK_FAILED`, `SQS_BATCH_SIZE`, and `POLL_INTERVAL_SECONDS`, which may hold their real literal values.

### Phase 2. Contracts

Lock the signatures and constant names to the tables above. Stop if a signature contradicts Issue 193 (shared code in `lib/aws/`, app classes inherit later).

### Phase 3. Test design (failing)

Write tests under `tests/lib/aws/` using a FakeClient or a monkeypatched `boto3.client`. No live AWS. Follow UNIT_TESTING_STANDARDS (`Test{Name}` classes, arrange-act-assert, `result` / `expected`).

`tests/lib/aws/test_clients.py`

1. **Given** a `ClientError` whose `Error.Code` is `ConditionalCheckFailedException` **when** `error_code` **then** the return value is that string.
2. **Given** a `ClientError` whose `Error` mapping is missing **when** `error_code` **then** the return value is `""`.
3. **Given** `service_name="dynamodb"`, `region="us-east-2"`, `config=None` **when** `build_client` **then** `boto3.client` is called with `region_name="us-east-2"` and without a `config` keyword.
4. **Given** a `botocore.config.Config` instance **when** `build_client` **then** `boto3.client` is called with that object as `config`.
5. **Given** each of `build_dynamodb_client`, `build_sqs_client`, `build_s3_client`, `build_athena_client` **when** called with a region and `None` config **then** `boto3.client` is called with `"dynamodb"`, `"sqs"`, `"s3"`, or `"athena"` respectively.

`tests/lib/aws/test_dynamodb.py`

1. **Given** `table="t"` and a fake client **when** `DynamoDBStore` is constructed **then** `.table == "t"` and `.client` is the fake.
2. **Given** `client=None` **when** `DynamoDBStore` is constructed **then** `build_dynamodb_client` / `boto3.client` is used and `.client` is the object that call returned.

`tests/lib/aws/test_s3.py`

1. **Given** `s3_uri="s3://bucket/path/key.parquet"` and `expires_in=60` **when** `generate_presigned_url` **then** the fake client is called with `ClientMethod="get_object"`, `Params={"Bucket": "bucket", "Key": "path/key.parquet"}`, `ExpiresIn=60`, and the method returns the client's return value.

`tests/lib/aws/test_athena.py`

1. **Given** `get_query_execution` returns `SUCCEEDED` on the first poll **when** `run_query` **then** the return value is the execution id from `start_query_execution`, and `start_query_execution` was called with the given query, database, and workgroup.
2. **Given** `State="FAILED"` and `StateChangeReason="boom"` **when** `run_query` **then** `RuntimeError` is raised and the message includes `FAILED` and `boom`.
3. **Given** a completed execution id **when** `get_output_location` **then** the return value is the `OutputLocation` string.

`tests/lib/aws/test_sqs.py`

1. **Given** `queue_url="https://sqs.test/q"` **when** `SqsQueueBase` is constructed **then** `.queue_url` is that URL and `get_queue_url` is not called.
2. **Given** `queue_name="my-queue"` and no `queue_url` **when** constructed **then** `get_queue_url` is called with `QueueName="my-queue"` and `.queue_url` is the returned URL.
3. **Given** both `queue_url` and `queue_name` are `None` **when** constructed **then** `ValueError` is raised.
4. **Given** a list of entries **when** `send_message_batch` **then** the client is called with `QueueUrl=self.queue_url` and those `Entries`, and the method returns the client response.

### Phase 4 to 5

Do not flesh AWS call bodies in this step. Constants may be real literals. Constructor attribute assignment may be implemented if a test needs a constructable object. Methods that talk to AWS may still raise `NotImplementedError`.

## Must pass

The paths in "Files allowed to change" exist.

```bash
uv run pytest tests/lib/aws/ -q
```

The command must run. Tests may fail with `NotImplementedError` or assertion mismatch. They must not fail with `ImportError` or `ModuleNotFoundError`.

```bash
uv run python -c "from lib.aws.constants import AWS_REGION; print(AWS_REGION)"
```

Expected output:

```text
us-east-2
```

## Must fail or must not happen

1. No file under `bluesky_ingestion_jetstream/`, `bluesky_backfill_app/`, `backend/`, or `data_platform/` is modified.
2. No test opens a real AWS network connection.
3. `lib/aws/` does not define Glue, Iceberg, dead-letter, DID status, or cursor table names.
4. `S3` does not grow `upload_file`. `Athena` does not grow result paging or `ALTER TABLE` helpers.

## Done when

`lib/aws/` exists with frozen public names, and `tests/lib/aws/` encodes the contracts above. Ready for Step 2 to implement the AWS call bodies against those tests.
