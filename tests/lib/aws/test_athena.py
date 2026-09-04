from __future__ import annotations

import pytest

from lib.aws.athena import Athena


class FakeAthenaClient:
    def __init__(self, statuses: list[dict]) -> None:
        self.statuses = list(statuses)
        self.start_calls: list[dict] = []
        self.get_calls: list[str] = []
        self.output_location = "s3://results/qid-1.csv"

    def start_query_execution(self, **kwargs):
        self.start_calls.append(kwargs)
        return {"QueryExecutionId": "qid-1"}

    def get_query_execution(self, QueryExecutionId: str):  # noqa: N803
        self.get_calls.append(QueryExecutionId)
        status = self.statuses.pop(0)
        return {
            "QueryExecution": {
                "Status": status,
                "ResultConfiguration": {"OutputLocation": self.output_location},
            }
        }


class TestRunQuery:
    """Tests for Athena.run_query."""

    def test_returns_execution_id_when_succeeded(self, monkeypatch: pytest.MonkeyPatch):
        client = FakeAthenaClient(statuses=[{"State": "SUCCEEDED"}])
        athena = Athena(client=client)
        monkeypatch.setattr("lib.aws.athena.time.sleep", lambda _seconds: None)

        result = athena.run_query("SELECT 1", "db", "wg")
        expected = "qid-1"

        assert result == expected
        assert client.start_calls == [
            {
                "QueryString": "SELECT 1",
                "QueryExecutionContext": {"Database": "db"},
                "WorkGroup": "wg",
            }
        ]

    def test_raises_runtime_error_when_failed(self, monkeypatch: pytest.MonkeyPatch):
        client = FakeAthenaClient(statuses=[{"State": "FAILED", "StateChangeReason": "boom"}])
        athena = Athena(client=client)
        monkeypatch.setattr("lib.aws.athena.time.sleep", lambda _seconds: None)

        with pytest.raises(RuntimeError, match="FAILED") as exc_info:
            athena.run_query("SELECT 1", "db", "wg")

        assert "boom" in str(exc_info.value)


class TestGetOutputLocation:
    """Tests for Athena.get_output_location."""

    def test_returns_output_location(self):
        client = FakeAthenaClient(statuses=[{"State": "SUCCEEDED"}])
        athena = Athena(client=client)

        result = athena.get_output_location("qid-1")
        expected = "s3://results/qid-1.csv"

        assert result == expected
