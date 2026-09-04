from __future__ import annotations

import pytest

from lib.aws.dynamodb import DynamoDB


class FakeDynamoClient:
    pass


class TestDynamoDB:
    """Tests for DynamoDB construction."""

    def test_stores_injected_client_and_table(self):
        client = FakeDynamoClient()

        result = DynamoDB(table="t", client=client)

        assert result.table == "t"
        assert result.client is client

    def test_builds_a_client_when_none_is_passed(self, monkeypatch: pytest.MonkeyPatch):
        built = FakeDynamoClient()
        calls: list[tuple[str, object]] = []

        def fake_build(region, config):
            calls.append((region, config))
            return built

        monkeypatch.setattr("lib.aws.dynamodb.build_dynamodb_client", fake_build)

        result = DynamoDB(table="t")

        assert result.client is built
        assert result.table == "t"
        assert calls == [("us-east-2", None)]
