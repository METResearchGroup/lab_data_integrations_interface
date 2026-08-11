"""Timed DynamoDB PutItem and BatchWriteItem helpers for the rates experiment.

Run from repo root:

    PYTHONPATH=. uv run python experiments/dynamodb_rates_2026_08_11/main.py
"""

from __future__ import annotations

import time
from typing import Any

import boto3

from experiments.dynamodb_rates_2026_08_11.config import (
    AWS_REGION,
    BATCH_WRITE_LIMIT,
    ITEM_COUNT,
    PARTITION_KEY,
    TABLE_NAME,
)

UNPROCESSED_RETRY_SLEEP_SECONDS = 0.05
MAX_UNPROCESSED_RETRIES = 100


def make_client() -> Any:
    """Return a DynamoDB low-level client for the experiment region."""
    return boto3.client("dynamodb", region_name=AWS_REGION)


def make_keys(*, run_id: str, ablation: str, count: int = ITEM_COUNT) -> list[str]:
    """Build unique AT Protocol style URI keys for one ablation.

    Parameters
    ----------
    run_id
        Timestamp string that identifies this experiment run.
    ablation
        Ablation label embedded in each URI, typically ``single`` or ``batch``.
    count
        Number of keys to generate.

    Returns
    -------
    list[str]
        ``count`` unique URI strings that share ``run_id`` and ``ablation``.
    """
    return [
        f"at://did:plc:ddbrates{run_id}/app.bsky.feed.post/{ablation}/{index:04d}"
        for index in range(count)
    ]


def run_single_puts(client: Any, keys: list[str]) -> dict[str, float | int]:
    """Write each key with PutItem and return wall clock timing.

    Parameters
    ----------
    client
        boto3 DynamoDB client.
    keys
        Partition key values to put.

    Returns
    -------
    dict[str, float | int]
        ``duration_seconds``, ``http_calls``, and ``items_written``.

    Raises
    ------
    Exception
        Propagates the first PutItem failure from boto3.
    """
    started = time.perf_counter()
    http_calls = 0
    for key in keys:
        client.put_item(
            TableName=TABLE_NAME,
            Item={PARTITION_KEY: {"S": key}},
        )
        http_calls += 1
    duration_seconds = time.perf_counter() - started
    return {
        "duration_seconds": duration_seconds,
        "http_calls": http_calls,
        "items_written": len(keys),
    }


def run_batch_writes(client: Any, keys: list[str]) -> dict[str, float | int]:
    """Write keys with BatchWriteItem PutRequest chunks and return timing.

    Retries ``UnprocessedItems`` after a short sleep. Counts every
    ``batch_write_item`` call, including retries.

    Parameters
    ----------
    client
        boto3 DynamoDB client.
    keys
        Partition key values to put.

    Returns
    -------
    dict[str, float | int]
        ``duration_seconds``, ``http_calls``, and ``items_written``.
    """
    started = time.perf_counter()
    http_calls = 0
    for offset in range(0, len(keys), BATCH_WRITE_LIMIT):
        chunk = keys[offset : offset + BATCH_WRITE_LIMIT]
        request_items = {
            TABLE_NAME: [{"PutRequest": {"Item": {PARTITION_KEY: {"S": key}}}} for key in chunk]
        }
        http_calls += _batch_write_until_done(client, request_items)
    duration_seconds = time.perf_counter() - started
    return {
        "duration_seconds": duration_seconds,
        "http_calls": http_calls,
        "items_written": len(keys),
    }


def teardown_keys(client: Any, keys: list[str]) -> dict[str, int]:
    """Delete the given keys with BatchWriteItem DeleteRequest chunks.

    Retries ``UnprocessedItems`` after a short sleep. Does not scan or clear
    the whole table.

    Parameters
    ----------
    client
        boto3 DynamoDB client.
    keys
        Partition key values to delete.

    Returns
    -------
    dict[str, int]
        ``http_calls`` and ``items_deleted``.
    """
    if not keys:
        return {"http_calls": 0, "items_deleted": 0}

    http_calls = 0
    for offset in range(0, len(keys), BATCH_WRITE_LIMIT):
        chunk = keys[offset : offset + BATCH_WRITE_LIMIT]
        request_items = {
            TABLE_NAME: [{"DeleteRequest": {"Key": {PARTITION_KEY: {"S": key}}}} for key in chunk]
        }
        http_calls += _batch_write_until_done(client, request_items)
    return {"http_calls": http_calls, "items_deleted": len(keys)}


def _batch_write_until_done(client: Any, request_items: dict[str, list[dict[str, Any]]]) -> int:
    """Submit one BatchWriteItem and retry until no unprocessed items remain.

    Returns
    -------
    int
        Number of ``batch_write_item`` HTTP calls made for this request set.

    Raises
    ------
    TimeoutError
        When unprocessed items remain after ``MAX_UNPROCESSED_RETRIES`` retries.
    """
    http_calls = 0
    response = client.batch_write_item(RequestItems=request_items)
    http_calls += 1
    retries = 0
    while response.get("UnprocessedItems"):
        if retries >= MAX_UNPROCESSED_RETRIES:
            remaining = sum(len(items) for items in response["UnprocessedItems"].values())
            raise TimeoutError(
                "BatchWriteItem still had "
                f"{remaining} unprocessed items after {MAX_UNPROCESSED_RETRIES} retries"
            )
        time.sleep(UNPROCESSED_RETRY_SLEEP_SECONDS)
        response = client.batch_write_item(RequestItems=response["UnprocessedItems"])
        http_calls += 1
        retries += 1
    return http_calls
