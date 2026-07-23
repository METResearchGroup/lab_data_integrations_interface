from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from data_platform.aws import dynamodb as dynamodb_mod
from data_platform.aws.dynamodb import DynamoDB


@pytest.fixture
def mock_table(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    table = MagicMock()
    resource = MagicMock()
    resource.Table.return_value = table
    monkeypatch.setattr(dynamodb_mod.boto3, "resource", lambda *args, **kwargs: resource)
    return table


def test_put_item_passes_item_through(mock_table: MagicMock) -> None:
    DynamoDB().put_item("my-table", {"id": "1", "status": "completed"})
    mock_table.put_item.assert_called_once_with(Item={"id": "1", "status": "completed"})


def test_get_item_returns_item_when_present(mock_table: MagicMock) -> None:
    mock_table.get_item.return_value = {"Item": {"id": "1", "status": "ok"}}
    assert DynamoDB().get_item("my-table", {"id": "1"}) == {"id": "1", "status": "ok"}
    mock_table.get_item.assert_called_once_with(Key={"id": "1"})


def test_get_item_returns_none_when_missing(mock_table: MagicMock) -> None:
    mock_table.get_item.return_value = {}
    assert DynamoDB().get_item("my-table", {"id": "missing"}) is None


def test_update_item_builds_expression_for_single_attribute(mock_table: MagicMock) -> None:
    DynamoDB().update_item("my-table", {"id": "1"}, {"status": "completed"})
    mock_table.update_item.assert_called_once_with(
        Key={"id": "1"},
        UpdateExpression="SET #n0_0 = :v0",
        ExpressionAttributeNames={"#n0_0": "status"},
        ExpressionAttributeValues={":v0": "completed"},
    )


def test_update_item_builds_expression_for_nested_attribute(mock_table: MagicMock) -> None:
    DynamoDB().update_item(
        "my-table",
        {"id": "1"},
        {"stages.ingestion": {"run_id": "r1", "status": "completed"}},
    )
    mock_table.update_item.assert_called_once_with(
        Key={"id": "1"},
        UpdateExpression="SET #n0_0.#n0_1 = :v0",
        ExpressionAttributeNames={"#n0_0": "stages", "#n0_1": "ingestion"},
        ExpressionAttributeValues={":v0": {"run_id": "r1", "status": "completed"}},
    )


def test_update_item_handles_multiple_attributes_independently(mock_table: MagicMock) -> None:
    DynamoDB().update_item(
        "my-table",
        {"id": "1"},
        {"status": "completed", "completed_at": "2026_01_01-00:00:00"},
    )
    mock_table.update_item.assert_called_once_with(
        Key={"id": "1"},
        UpdateExpression="SET #n0_0 = :v0, #n1_0 = :v1",
        ExpressionAttributeNames={"#n0_0": "status", "#n1_0": "completed_at"},
        ExpressionAttributeValues={":v0": "completed", ":v1": "2026_01_01-00:00:00"},
    )
