"""Show DynamoDB batch behavior when one request in the batch is invalid.

Question
--------
If ``BatchWriteItem`` or ``BatchGetItem`` includes one invalid key or item
alongside valid ones, does the whole batch fail, or only the bad request?

Answer (live against the experiment table)
------------------------------------------
The whole API call fails with ``ValidationException``. None of the valid
puts in that same ``BatchWriteItem`` are applied.

Run from repo root:

    PYTHONPATH=. uv run pytest \\
        tests/experiments/dynamodb_rates_2026_08_11/test_batch_invalid_item.py -q
"""

from __future__ import annotations

import os
import uuid

import boto3
import pytest
from botocore.exceptions import ClientError

from experiments.dynamodb_rates_2026_08_11.config import (
    AWS_REGION,
    PARTITION_KEY,
    TABLE_NAME,
)


def _require_live_dynamodb() -> None:
    if not os.environ.get("AWS_ACCESS_KEY_ID"):
        pytest.skip("AWS_ACCESS_KEY_ID is not set")


@pytest.fixture
def dynamodb_client():
    _require_live_dynamodb()
    client = boto3.client("dynamodb", region_name=AWS_REGION)
    try:
        client.describe_table(TableName=TABLE_NAME)
    except ClientError as exc:
        pytest.skip(f"Experiment table unavailable: {exc}")
    return client


class TestBatchWriteItemWithOneInvalidPut:
    """Test BatchWriteItem when one PutRequest is schema-invalid."""

    def test_entire_batch_write_fails_and_valid_item_is_not_written(self, dynamodb_client) -> None:
        """One bad PutRequest rejects the whole BatchWriteItem.

        The valid sibling item in the same request must not appear in the table.
        """
        valid_key = (
            f"at://did:plc:ddbrates-batch-invalid-{uuid.uuid4().hex}/app.bsky.feed.post/probe/valid"
        )

        with pytest.raises(ClientError) as raised:
            dynamodb_client.batch_write_item(
                RequestItems={
                    TABLE_NAME: [
                        {
                            "PutRequest": {
                                "Item": {PARTITION_KEY: {"S": valid_key}},
                            }
                        },
                        {
                            "PutRequest": {
                                # Invalid: partition key must be ``uri``, not ``not_uri``.
                                "Item": {"not_uri": {"S": "bad"}},
                            }
                        },
                    ]
                }
            )

        error = raised.value.response["Error"]
        assert error["Code"] == "ValidationException"
        assert "schema" in error["Message"].lower()

        got = dynamodb_client.get_item(
            TableName=TABLE_NAME,
            Key={PARTITION_KEY: {"S": valid_key}},
        )
        assert "Item" not in got


class TestBatchGetItemWithOneInvalidKey:
    """Test BatchGetItem when one key is schema-invalid."""

    def test_entire_batch_get_fails(self, dynamodb_client) -> None:
        """One bad key rejects the whole BatchGetItem call."""
        valid_key = (
            f"at://did:plc:ddbrates-batch-invalid-{uuid.uuid4().hex}/app.bsky.feed.post/probe/get"
        )

        with pytest.raises(ClientError) as raised:
            dynamodb_client.batch_get_item(
                RequestItems={
                    TABLE_NAME: {
                        "Keys": [
                            {PARTITION_KEY: {"S": valid_key}},
                            {"not_uri": {"S": "bad"}},
                        ]
                    }
                }
            )

        error = raised.value.response["Error"]
        assert error["Code"] == "ValidationException"
        assert "schema" in error["Message"].lower()
