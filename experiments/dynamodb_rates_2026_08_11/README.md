# DynamoDB single put vs batch write rates (2026-08-11)

## Summary

This experiment times two ways of writing 1000 items to the DynamoDB table `lab-data-integrations-dedup-experiment-seen-ids` in `us-east-2`. Ablation 1 sends 1000 individual PutItem requests. Ablation 2 writes the same count of items with BatchWriteItem. The script prints wall clock duration and HTTP call counts for each ablation, then deletes every key it wrote.

## Results

Live run `2026_08_11-14:36:12`:

| Condition | Duration (s) | HTTP calls | Items written |
| --------- | -----------: | ---------: | ------------: |
| Ablation 1 PutItem | 5.572 | 1000 | 1000 |
| Ablation 2 BatchWriteItem | 0.291 | 40 | 1000 |

BatchWriteItem finished about 19 times faster than serial PutItem for 1000 items, and used 40 HTTP calls instead of 1000. Prefer BatchWriteItem for write batches of this size.

## How to run

### Prerequisites

1. Install dependencies from the repo root (boto3 is already a project dependency).

```bash
uv sync
```

2. Set AWS credentials that can put and delete items on the experiment table, and use region `us-east-2`. Temporary credentials also need `AWS_SESSION_TOKEN`.

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-2
```

3. Confirm the shared experiment table exists. The table name is `lab-data-integrations-dedup-experiment-seen-ids` (partition key `uri`, pay per request). The schema matches `experiments/dedup_comparison_2026_06_12/terraform/main.tf`. If the table is missing, recreate it with that schema before running.

### Run command

From the repo root:

```bash
PYTHONPATH=. uv run python experiments/dynamodb_rates_2026_08_11/main.py
```

### Expected stdout

```text
Ablation 1 (1000 PutItem) took X.XXXs across 1000 HTTP calls
Ablation 2 (1000 BatchWriteItem) took Y.YYYs across N HTTP calls
Teardown complete, 2000 keys deleted
```

Results JSON is written under `experiments/dynamodb_rates_2026_08_11/data/<run_id>/results.json`.

## Teardown

Teardown deletes only the keys created in the current run (1000 single-put keys plus 1000 batch-write keys). The script does not clear the whole table.
