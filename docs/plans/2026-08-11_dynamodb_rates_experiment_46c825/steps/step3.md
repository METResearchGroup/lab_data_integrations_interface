# Step 3. Wire the entrypoint and results output

Wire `main.py` so an operator can run both ablations end to end, see timings, save JSON results, and always tear down the experiment keys.

## Scope

- **Caller.** Repo root command

```bash
PYTHONPATH=. uv run python experiments/dynamodb_rates_2026_08_11/main.py
```

- **Slice.** Generate keys, run Ablation 1, run Ablation 2, print comparison, write results JSON, tear down all keys from the run.
- **Out of scope.** pytest, Terraform, cost modeling, Rich tables, argparse flags beyond what you need for a default full run.

## Files to inspect

- `experiments/dynamodb_rates_2026_08_11/config.py`
- `experiments/dynamodb_rates_2026_08_11/writes.py`
- `experiments/dynamodb_rates_2026_08_11/README.md`
- `lib/timestamp_utils.py` for `get_current_timestamp`
- `experiments/x_fetch_data_2026_06_01/main.py` for timestamped `data/` directory creation and simple metadata JSON writing

## Files allowed to change

- `experiments/dynamodb_rates_2026_08_11/main.py` (create)
- `experiments/dynamodb_rates_2026_08_11/README.md` (update if the documented stdout or output paths need to match the real script)

## Files forbidden to change

- `experiments/dynamodb_rates_2026_08_11/writes.py` except for a bug fix found while wiring the caller
- `experiments/dedup_comparison_2026_06_12/**`
- Any file under `data_platform/`
- Any file under `tests/`
- Terraform files
- `pyproject.toml`

## Caller path

1. Read `ITEM_COUNT` and related constants from config.
2. Build a DynamoDB client the same way `writes.py` expects, or call a small factory in `writes.py` if you added one in Step 2.
3. `run_id = get_current_timestamp()`.
4. `single_keys = make_keys(run_id=run_id, ablation="single")`.
5. `batch_keys = make_keys(run_id=run_id, ablation="batch")`.
6. Create `experiments/dynamodb_rates_2026_08_11/data/{run_id}/`.
7. Inside a `try` / `finally` block, do the work below.
   - Run `run_single_puts(client, single_keys)` and print duration and HTTP calls.
   - Run `run_batch_writes(client, batch_keys)` and print duration and HTTP calls.
   - Write `results.json` with table name, region, item count, both ablation result dicts, and both key lists or at least the key counts.
   - In `finally`, call `teardown_keys(client, single_keys + batch_keys)` and print how many keys were deleted.

The `finally` block is required so a failure in Ablation 2 still deletes Ablation 1 keys.

## results.json shape

Write a JSON object with at least the fields below.

- `run_id`
- `table_name`
- `region`
- `item_count`
- `ablation_1_single_put` with `duration_seconds`, `http_calls`, `items_written`
- `ablation_2_batch_write` with `duration_seconds`, `http_calls`, `items_written`
- `teardown` with `items_deleted`, `http_calls`

Do not commit the `data/` directory contents. Add `experiments/dynamodb_rates_2026_08_11/data/` to ignore rules only if the repo already ignores sibling experiment `data/` dirs the same way. If sibling experiments leave `data/` untracked without a local ignore entry, follow that existing practice and do not add a new ignore file unless needed.

## Must pass

The command below must compile.

```bash
PYTHONPATH=. uv run python -m py_compile experiments/dynamodb_rates_2026_08_11/main.py
```

Expected result is exit code 0 and no output.

With AWS credentials and `AWS_DEFAULT_REGION=us-east-2` or region set via the client, a live run of

```bash
PYTHONPATH=. uv run python experiments/dynamodb_rates_2026_08_11/main.py
```

must print Ablation 1 duration, Ablation 2 duration, and a teardown line. The live run must also write `experiments/dynamodb_rates_2026_08_11/data/<run_id>/results.json`.

After a successful live run, none of the run keys remain in the table. You can confirm by batch getting a sample of the keys from `results.json`, or by logging that teardown deleted `2 * ITEM_COUNT` keys.

The `README.md` run command must match the live entrypoint.

## Must fail or must not happen

1. No pytest files under `tests/experiments/dynamodb_rates_2026_08_11/` or inside the experiment folder.
2. No path that skips teardown after keys were created.
3. No write to any DynamoDB table other than `lab-data-integrations-dedup-experiment-seen-ids`.
4. Do not commit result JSON from a live run unless the operator explicitly asks to keep a checked in sample later.
