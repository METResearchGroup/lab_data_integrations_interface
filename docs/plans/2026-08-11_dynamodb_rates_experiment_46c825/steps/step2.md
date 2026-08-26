# Step 2. Implement timed ablations and teardown

Add the write helpers that time Ablation 1, time Ablation 2, and delete the keys this experiment wrote. Keep `main.py` for Step 3.

## Scope

- **Caller.** `experiments/dynamodb_rates_2026_08_11/main.py` (Step 3) will call these helpers. In this step you prove the helpers by importing them and calling them from a short manual check if AWS credentials are present.
- **Slice.** Key generation, single put ablation, batch write ablation, and teardown.
- **Out of scope.** `main.py` results JSON orchestration, README edits beyond a one line fix if a constant name changed, Terraform, pytest.

## Files to inspect

- `experiments/dynamodb_rates_2026_08_11/config.py` from Step 1
- `experiments/dedup_comparison_2026_06_12/dynamodb_backend.py` for `batch_write_item`, unprocessed item retry with `time.sleep(0.05)`, and `cleanup` delete shape
- `docs/plans/2026-08-11_dynamodb_rates_experiment_46c825/steps/step1.md` for the frozen key URI shape

## Files allowed to change

- `experiments/dynamodb_rates_2026_08_11/writes.py` (create)
- `experiments/dynamodb_rates_2026_08_11/config.py` (only if a constant from Step 1 must be corrected)

## Files forbidden to change

- `experiments/dynamodb_rates_2026_08_11/main.py` (Step 3 owns this file)
- `experiments/dedup_comparison_2026_06_12/**`
- Any file under `data_platform/`
- Any file under `tests/`
- Terraform files

## Contracts to freeze in writes.py

Create a DynamoDB client with `boto3.client("dynamodb", region_name=AWS_REGION)`.

### make_keys

```python
def make_keys(*, run_id: str, ablation: str, count: int = ITEM_COUNT) -> list[str]: ...
```

Returns `count` unique URI strings using the Step 1 shape. `ablation` is `"single"` or `"batch"`. Ablation 1 and Ablation 2 must use different ablation labels so the two key sets are disjoint. You get a fair timing comparison when the key sets are disjoint, because Ablation 2 does not overwrite Ablation 1 items.

### run_single_puts

```python
def run_single_puts(client, keys: list[str]) -> dict[str, float | int]: ...
```

For each key, call `put_item` with `Item={PARTITION_KEY: {"S": key}}`. Time the full loop with `time.perf_counter()`. Return at least the fields below.

- `duration_seconds` as float
- `http_calls` as int, equal to `len(keys)` when every put succeeds
- `items_written` as int, equal to `len(keys)`

If any put raises, let the exception propagate. Step 3 can still tear down keys already written. `run_single_puts` itself may raise on the first failure.

### run_batch_writes

```python
def run_batch_writes(client, keys: list[str]) -> dict[str, float | int]: ...
```

Write keys in chunks of `BATCH_WRITE_LIMIT` with `batch_write_item` and `PutRequest` items. When the response contains `UnprocessedItems`, sleep 0.05 seconds and retry those items, matching `experiments/dedup_comparison_2026_06_12/dynamodb_backend.py`. Count every `batch_write_item` call, including retries, in `http_calls`. Return the same result keys as `run_single_puts`.

For 1000 items and no unprocessed retries, expected `http_calls` is `ceil(1000 / 25) = 40`.

### teardown_keys

```python
def teardown_keys(client, keys: list[str]) -> dict[str, int]: ...
```

Delete the given keys with `batch_write_item` and `DeleteRequest`, chunked by `BATCH_WRITE_LIMIT`, with the same unprocessed item retry. Return at least `http_calls` and `items_deleted` (`len(keys)` when every key was submitted for delete). Callers pass the union of Ablation 1 and Ablation 2 keys.

## Implementation notes

1. Do not clear the whole table. Only delete keys this experiment created.
2. Do not use a thread pool. Keep both ablations single threaded so the timing comparison is easy to read.
3. Do not add cost estimates.
4. Do not import from `experiments/dedup_comparison_2026_06_12/`. Copy only the small retry pattern, so this experiment stays self contained.

## Must pass

The command below must exit 0.

```bash
PYTHONPATH=. uv run python -c "from experiments.dynamodb_rates_2026_08_11.writes import make_keys, run_single_puts, run_batch_writes, teardown_keys; print(len(make_keys(run_id='2026_08_11-00:00:00', ablation='single')))"
```

Expected output is below.

```text
1000
```

`make_keys` for `ablation="single"` and `ablation="batch"` with the same `run_id` must return two lists with empty intersection.

With AWS credentials set, a manual smoke of 2 keys for each helper must write then delete without leaving those keys in the table. You do not need to run the full 1000 count in this step.

## Must fail or must not happen

1. No `clear_all` or full table scan delete.
2. No file under `tests/`.
3. No call to a table other than `TABLE_NAME` from config.
4. Batch writes must not send more than 25 items in one `RequestItems` list.
