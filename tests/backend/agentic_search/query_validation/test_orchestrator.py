"""validate_query wiring, with the extraction stubbed out."""

from __future__ import annotations

from datetime import date

import pytest

from backend.agentic_search.query_validation.models import TableMetadata, ValidationIssue
from backend.agentic_search.query_validation.orchestrator import validate_query
from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.constants import RecordType

MODULE = "backend.agentic_search.query_validation.orchestrator"


@pytest.fixture
def stub(
    monkeypatch: pytest.MonkeyPatch,
    snapshot: dict[RecordType, TableMetadata],
):
    """Pin the snapshot and let each test choose what the extraction returns."""

    def _stub(intent: QueryIntent) -> None:
        monkeypatch.setattr(f"{MODULE}.build_snapshot", lambda: snapshot)
        monkeypatch.setattr(f"{MODULE}.extract_intent", lambda _query, _snapshot: intent)

    return _stub


def test_clean_query_is_valid(stub) -> None:
    stub(
        QueryIntent(
            is_nonsense=False,
            record_type=RecordType.POSTS,
            columns=["langs", "created_at"],
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
    )
    result = validate_query("how many posts were written in Spanish in July")
    assert result.valid
    assert result.issues == []


def test_nonsense_short_circuits_the_other_checks(stub) -> None:
    """record_type is None here, but only NONSENSE comes back."""

    stub(
        QueryIntent(
            is_nonsense=True,
            record_type=None,
            columns=[],
            start_date=None,
            end_date=None,
        )
    )
    result = validate_query("what's the weather in Tokyo")
    assert not result.valid
    assert result.issues == [ValidationIssue.NONSENSE]


def test_issues_from_both_checks_are_collected(stub) -> None:
    stub(
        QueryIntent(
            is_nonsense=False,
            record_type=RecordType.FOLLOWS,
            columns=["like_count"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
    )
    result = validate_query("who followed whom in January, by like count")
    assert not result.valid
    assert result.issues == [
        ValidationIssue.UNKNOWN_COLUMN,
        ValidationIssue.RANGE_OUTSIDE_COVERAGE,
    ]
