"""Shared constants for the DynamoDB single-put vs batch-write rate experiment.

Run from repo root:

    PYTHONPATH=. uv run python experiments/dynamodb_rates_2026_08_11/main.py
"""

TABLE_NAME = "lab-data-integrations-dedup-experiment-seen-ids"
AWS_REGION = "us-east-2"
PARTITION_KEY = "uri"
ITEM_COUNT = 1000
BATCH_WRITE_LIMIT = 25
KEY_PREFIX = "experiment/dynamodb_rates_2026_08_11"
