# Step 1. Scaffold the experiment package

Create the experiment package layout, README run instructions, and shared constants that point at the existing DynamoDB table. Do not write ablation logic yet.

## Scope

- **Caller.** Later `experiments/dynamodb_rates_2026_08_11/main.py` will import constants from this package. In this step the caller is not wired yet.
- **Slice.** Package marker, constants module, and README only.
- **Out of scope.** PutItem and BatchWriteItem logic, teardown, results JSON, Terraform, pytest, and any production table.

## Files to inspect

- `experiments/dedup_comparison_2026_06_12/dynamodb_backend.py` for the existing table name and boto3 client usage
- `experiments/dedup_comparison_2026_06_12/terraform/main.tf` for table name, region, partition key, and billing mode
- `experiments/dedup_comparison_2026_06_12/README.md` for AWS credential and region setup wording
- `experiments/x_fetch_data_2026_06_01/README.md` for a short experiment README shape
- `lib/timestamp_utils.py` for the shared timestamp helper used by later steps

## Files allowed to change

- `experiments/dynamodb_rates_2026_08_11/__init__.py` (create, empty package marker)
- `experiments/dynamodb_rates_2026_08_11/config.py` (create)
- `experiments/dynamodb_rates_2026_08_11/README.md` (create)

## Files forbidden to change

- `experiments/dedup_comparison_2026_06_12/**`
- `experiments/dedup_comparison_2026_06_12/terraform/**`
- Any file under `data_platform/`
- Any file under `tests/`
- `pyproject.toml`

## What to put in config.py

Freeze these constants before Step 2.

- `TABLE_NAME = "lab-data-integrations-dedup-experiment-seen-ids"`
- `AWS_REGION = "us-east-2"`
- `PARTITION_KEY = "uri"`
- `ITEM_COUNT = 1000`
- `BATCH_WRITE_LIMIT = 25` (DynamoDB BatchWriteItem max items per request)
- `KEY_PREFIX = "experiment/dynamodb_rates_2026_08_11"` so every written key is easy to identify and delete

The partition key values are strings that look like AT Protocol URIs and embed a DID segment unique to the run. An example shape is
`at://did:plc:ddbrates{run_id}/app.bsky.feed.post/{ablation}/{index:04d}`.

`run_id` comes from `lib.timestamp_utils.get_current_timestamp()` in Step 3. Ablation labels are `single` and `batch`.

## What to put in README.md

Document the items below.

1. Purpose of the two ablations
2. Prerequisites (`uv sync` if needed for boto3, AWS credentials, `AWS_DEFAULT_REGION=us-east-2`)
3. The exact run command from the repo root
4. That teardown deletes only keys from the current run
5. That the shared experiment table already exists and no Terraform is required for this experiment

Document this exact run command.

```bash
PYTHONPATH=. uv run python experiments/dynamodb_rates_2026_08_11/main.py
```

Document the target stdout shape after Step 3 is complete. Step 1 does not print those lines yet.

```text
Ablation 1 (1000 PutItem) took X.XXXs across 1000 HTTP calls
Ablation 2 (1000 BatchWriteItem) took Y.YYYs across N HTTP calls
Teardown complete, 2000 keys deleted
```

## Must pass

The paths below must exist.

- `experiments/dynamodb_rates_2026_08_11/__init__.py`
- `experiments/dynamodb_rates_2026_08_11/config.py`
- `experiments/dynamodb_rates_2026_08_11/README.md`

The command below must exit 0 and print the table name.

```bash
PYTHONPATH=. uv run python -c "from experiments.dynamodb_rates_2026_08_11.config import TABLE_NAME; print(TABLE_NAME)"
```

Expected output is below.

```text
lab-data-integrations-dedup-experiment-seen-ids
```

`README.md` must contain the exact run command above and must name the existing table.

## Must fail or must not happen

1. No new Terraform file under `experiments/dynamodb_rates_2026_08_11/`.
2. No file under `tests/experiments/dynamodb_rates_2026_08_11/`.
3. `config.py` must not hardcode a production table name. The only allowed table name is `lab-data-integrations-dedup-experiment-seen-ids`.
