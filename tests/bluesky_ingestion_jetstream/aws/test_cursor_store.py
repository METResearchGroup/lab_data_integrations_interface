"""Tests for the DynamoDB cursor item, against a stub client."""

import logging

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from bluesky_ingestion_jetstream.aws.constants import (
    CURSOR_ATTRIBUTE,
    CURSOR_PARTITION_KEY,
    CURSOR_STREAM_ID,
    CURSOR_TABLE,
)
from bluesky_ingestion_jetstream.aws.cursor_store import DynamoCursorStore
from tests.bluesky_ingestion_jetstream.conftest import RUN_ID

CURSOR = 1784789293411372


def client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "UpdateItem")


class FakeClient:
    """Records calls and replays canned responses or errors."""

    def __init__(self, item: dict | None = None, error: Exception | None = None) -> None:
        self.item = item
        self.error = error
        self.get_calls: list[dict] = []
        self.update_calls: list[dict] = []

    def get_item(self, **kwargs):
        self.get_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"Item": self.item} if self.item else {}

    def update_item(self, **kwargs):
        self.update_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {}


def build_store(client: FakeClient) -> DynamoCursorStore:
    return DynamoCursorStore(RUN_ID, client=client)


class TestRead:
    def test_returns_the_stored_cursor(self):
        client = FakeClient(item={CURSOR_ATTRIBUTE: {"N": str(CURSOR)}})

        assert build_store(client).read() == CURSOR

    def test_a_missing_item_is_a_cold_start(self):
        assert build_store(FakeClient()).read() is None

    def test_addresses_the_configured_item(self):
        client = FakeClient()

        build_store(client).read()

        assert client.get_calls[0]["TableName"] == CURSOR_TABLE
        assert client.get_calls[0]["Key"] == {CURSOR_PARTITION_KEY: {"S": CURSOR_STREAM_ID}}

    def test_reads_consistently(self):
        """An eventually consistent read can hand back a cursor we already passed."""

        client = FakeClient()

        build_store(client).read()

        assert client.get_calls[0]["ConsistentRead"] is True

    def test_a_failed_read_raises_rather_than_starting_live(self):
        """Treating it as a cold start would skip everything since the last run."""

        client = FakeClient(error=EndpointConnectionError(endpoint_url="https://dynamodb"))

        with pytest.raises(EndpointConnectionError):
            build_store(client).read()

    def test_is_not_retried_above_the_client(self):
        """The client's own retries cover a blip; past those, exiting is the recovery."""

        client = FakeClient(error=client_error("ProvisionedThroughputExceededException"))

        with pytest.raises(ClientError):
            build_store(client).read()

        assert len(client.get_calls) == 1

    def test_a_permission_error_surfaces_immediately(self):
        """An IAM misconfiguration is permanent, and the likeliest first-deploy failure."""

        client = FakeClient(error=client_error("AccessDeniedException"))

        with pytest.raises(ClientError):
            build_store(client).read()

        assert len(client.get_calls) == 1


class TestWrite:
    def test_stores_the_cursor(self):
        client = FakeClient()

        build_store(client).write(CURSOR)

        values = client.update_calls[0]["ExpressionAttributeValues"]
        assert values[":cursor"] == {"N": str(CURSOR)}
        assert values[":run_id"] == {"S": RUN_ID}

    def test_refuses_to_move_the_cursor_backwards(self):
        client = FakeClient()

        build_store(client).write(CURSOR)

        condition = client.update_calls[0]["ConditionExpression"]
        assert f"attribute_not_exists({CURSOR_ATTRIBUTE})" in condition
        assert f"{CURSOR_ATTRIBUTE} < :cursor" in condition

    def test_a_stale_write_is_logged_not_raised(self, caplog):
        """A cursor further ahead than ours is information, not a failure."""

        client = FakeClient(error=client_error("ConditionalCheckFailedException"))

        with caplog.at_level(logging.WARNING):
            build_store(client).write(CURSOR)

        assert "already ahead" in caplog.text

    def test_other_failures_raise(self):
        """The tracker catches these; swallowing here would hide them from it."""

        client = FakeClient(error=client_error("ProvisionedThroughputExceededException"))

        with pytest.raises(ClientError):
            build_store(client).write(CURSOR)

    def test_is_not_retried_above_the_client(self):
        """Retrying stalls the read loop for a write whose failure costs a replay."""

        client = FakeClient(error=client_error("ProvisionedThroughputExceededException"))

        with pytest.raises(ClientError):
            build_store(client).write(CURSOR)

        assert len(client.update_calls) == 1
