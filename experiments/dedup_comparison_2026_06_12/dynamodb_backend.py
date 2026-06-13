"""DynamoDB deduplication backend.

Workflow per pipeline run:
  1. BatchGetItem: send current batch URIs, receive back which already exist
  2. Filter to new URIs
  3. BatchWriteItem: write new URIs to DynamoDB

Run from repo root:
    PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/dynamodb_backend.py
"""

from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3  # type: ignore[import-untyped]

TABLE_NAME = "lab-data-integrations-dedup-experiment-seen-ids"
_BATCH_GET_LIMIT = 100
_BATCH_WRITE_LIMIT = 25
_SEED_THREADS = 20


class DynamoDBBackend:
    def __init__(self, *, table_name: str = TABLE_NAME) -> None:
        self._table_name = table_name
        self._client = boto3.client("dynamodb")

    def seed(self, uris: list[str]) -> None:
        chunks = [uris[i : i + _BATCH_WRITE_LIMIT] for i in range(0, len(uris), _BATCH_WRITE_LIMIT)]

        def write_chunk(chunk: list[str]) -> None:
            request_items = {
                self._table_name: [{"PutRequest": {"Item": {"uri": {"S": u}}}} for u in chunk]
            }
            response = self._client.batch_write_item(RequestItems=request_items)
            while response.get("UnprocessedItems"):
                time.sleep(0.05)
                response = self._client.batch_write_item(RequestItems=response["UnprocessedItems"])

        with ThreadPoolExecutor(max_workers=_SEED_THREADS) as executor:
            futures = [executor.submit(write_chunk, chunk) for chunk in chunks]
            for future in as_completed(futures):
                future.result()

    def check(self, uris: list[str]) -> tuple[list[str], int]:
        already_seen: set[str] = set()
        http_calls = 0

        for i in range(0, len(uris), _BATCH_GET_LIMIT):
            chunk = uris[i : i + _BATCH_GET_LIMIT]
            response = self._client.batch_get_item(
                RequestItems={
                    self._table_name: {
                        "Keys": [{"uri": {"S": u}} for u in chunk],
                        "ProjectionExpression": "uri",
                    }
                }
            )
            http_calls += 1
            already_seen.update(
                item["uri"]["S"] for item in response["Responses"].get(self._table_name, [])
            )
            while response.get("UnprocessedKeys"):
                time.sleep(0.05)
                response = self._client.batch_get_item(RequestItems=response["UnprocessedKeys"])
                http_calls += 1
                already_seen.update(
                    item["uri"]["S"] for item in response["Responses"].get(self._table_name, [])
                )

        new_uris = [u for u in uris if u not in already_seen]
        return new_uris, http_calls

    def write(self, uris: list[str]) -> int:
        if not uris:
            return 0
        http_calls = 0
        for i in range(0, len(uris), _BATCH_WRITE_LIMIT):
            chunk = uris[i : i + _BATCH_WRITE_LIMIT]
            response = self._client.batch_write_item(
                RequestItems={
                    self._table_name: [{"PutRequest": {"Item": {"uri": {"S": u}}}} for u in chunk]
                }
            )
            http_calls += 1
            while response.get("UnprocessedItems"):
                time.sleep(0.05)
                response = self._client.batch_write_item(RequestItems=response["UnprocessedItems"])
                http_calls += 1
        return http_calls

    def cleanup(self, uris: list[str]) -> None:
        """Delete specific URIs (reset between benchmark runs)."""
        if not uris:
            return
        for i in range(0, len(uris), _BATCH_WRITE_LIMIT):
            chunk = uris[i : i + _BATCH_WRITE_LIMIT]
            response = self._client.batch_write_item(
                RequestItems={
                    self._table_name: [{"DeleteRequest": {"Key": {"uri": {"S": u}}}} for u in chunk]
                }
            )
            while response.get("UnprocessedItems"):
                time.sleep(0.05)
                response = self._client.batch_write_item(RequestItems=response["UnprocessedItems"])

    def clear_all(self) -> None:
        """Scan and delete every item in the table, with parallel deletes."""
        all_items: list[dict] = []
        scan_kwargs: dict = {"ProjectionExpression": "uri"}
        while True:
            response = self._client.scan(TableName=self._table_name, **scan_kwargs)
            all_items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

        if not all_items:
            return

        chunks = [
            all_items[i : i + _BATCH_WRITE_LIMIT]
            for i in range(0, len(all_items), _BATCH_WRITE_LIMIT)
        ]

        def delete_chunk(chunk: list[dict]) -> None:
            self._client.batch_write_item(
                RequestItems={
                    self._table_name: [
                        {"DeleteRequest": {"Key": {"uri": item["uri"]}}} for item in chunk
                    ]
                }
            )

        with ThreadPoolExecutor(max_workers=_SEED_THREADS) as executor:
            futures = [executor.submit(delete_chunk, chunk) for chunk in chunks]
            for future in as_completed(futures):
                future.result()

    @property
    def expected_check_calls(self) -> int:
        return math.ceil(1 / _BATCH_GET_LIMIT)

    def expected_write_calls(self, n_uris: int) -> int:
        return math.ceil(n_uris / _BATCH_WRITE_LIMIT)


def self_check() -> None:
    import os

    if not os.environ.get("AWS_DEFAULT_REGION"):
        print("SKIP: AWS_DEFAULT_REGION not set")
        return

    backend = DynamoDBBackend()
    backend.clear_all()
    backend.seed(["at://did:plc:abc/app.bsky.feed.post/001"])

    new_uris, calls = backend.check(
        [
            "at://did:plc:abc/app.bsky.feed.post/001",
            "at://did:plc:abc/app.bsky.feed.post/002",
        ]
    )
    assert new_uris == ["at://did:plc:abc/app.bsky.feed.post/002"], new_uris
    assert calls == 1

    write_calls = backend.write(new_uris)
    assert write_calls == 1

    backend.cleanup(new_uris)
    new_uris2, _ = backend.check(["at://did:plc:abc/app.bsky.feed.post/002"])
    assert new_uris2 == ["at://did:plc:abc/app.bsky.feed.post/002"]

    backend.clear_all()
    print("DynamoDBBackend SELF-CHECK PASS")


if __name__ == "__main__":
    self_check()
