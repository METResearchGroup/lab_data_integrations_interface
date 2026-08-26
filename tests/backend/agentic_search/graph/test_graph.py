"""Graph wiring, with the extraction and the AWS clients stubbed out."""

from __future__ import annotations

from datetime import date

import pytest

from backend.agentic_search.graph.graph import build_graph
from backend.agentic_search.graph.state import SearchState
from backend.agentic_search.query_validation.models import TableMetadata
from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.constants import RecordType

ORCHESTRATOR = "backend.agentic_search.query_validation.orchestrator"

EXECUTION_ID = "abc-123"
RESULT_URL = "https://example.invalid/result.csv"


class FakeAthena:
    def run_query(self, query: str, *, database: str, workgroup: str) -> str:
        self.sql = query
        return EXECUTION_ID

    def get_output_location(self, execution_id: str) -> str:
        return f"s3://results/{execution_id}.csv"


class FakeS3:
    def generate_presigned_url(self, s3_uri: str, *, expires_in: int) -> str:
        return RESULT_URL


@pytest.fixture
def snapshot() -> dict[RecordType, TableMetadata]:
    return {
        RecordType.POSTS: TableMetadata(
            columns=("uri", "author_did", "text", "langs", "created_at"),
            coverage_start=date(2026, 1, 1),
            coverage_end=date(2026, 8, 22),
        )
    }


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch, snapshot):
    def _stub(intent: QueryIntent) -> None:
        monkeypatch.setattr(f"{ORCHESTRATOR}.build_snapshot", lambda: snapshot)
        monkeypatch.setattr(f"{ORCHESTRATOR}.extract_intent", lambda _query, _snapshot: intent)

    return _stub


def test_valid_query_runs_all_three_stages(stub) -> None:
    stub(
        QueryIntent(
            is_nonsense=False,
            record_type=RecordType.POSTS,
            columns=["langs"],
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
    )
    state = build_graph(FakeAthena(), FakeS3()).invoke(SearchState(query="posts in July"))

    assert state["validation"].valid
    assert "SELECT" in state["generated"].sql
    assert state["executed"].execution_id == EXECUTION_ID
    assert state["executed"].result_url == RESULT_URL


def test_invalid_query_stops_before_generation(stub) -> None:
    """Nothing reaches Athena, so the fakes would raise if the routing were wrong."""

    stub(
        QueryIntent(
            is_nonsense=True,
            record_type=None,
            columns=[],
            start_date=None,
            end_date=None,
        )
    )
    state = build_graph(FakeAthena(), FakeS3()).invoke(SearchState(query="weather in Tokyo"))

    assert not state["validation"].valid
    assert state["generated"] is None
    assert state["executed"] is None
