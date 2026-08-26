"""process_query's three outcomes, with the graph and SES stubbed out."""

from __future__ import annotations

import pytest

from backend.agentic_search import process
from backend.agentic_search.query_execution.models import ExecutedQuery
from backend.agentic_search.query_validation.models import ValidationIssue, ValidationResult
from backend.agentic_search.query_validation.query_intent.models import QueryIntent

MODULE = "backend.agentic_search.process"

QUERY = "posts in July"
EMAIL = "someone@example.invalid"
RESULT_URL = "https://example.invalid/result.csv"


class FakeSES:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send(self, *, to: str, subject: str, body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body})


@pytest.fixture
def ses(monkeypatch: pytest.MonkeyPatch) -> FakeSES:
    fake = FakeSES()
    monkeypatch.setattr(f"{MODULE}._ses", lambda: fake)
    return fake


def _stub_graph(monkeypatch: pytest.MonkeyPatch, state: dict) -> None:
    class FakeGraph:
        def invoke(self, _state):
            return state

    monkeypatch.setattr(f"{MODULE}.build_graph", lambda _athena, _s3: FakeGraph())
    monkeypatch.setattr(f"{MODULE}.Athena", lambda: None)
    monkeypatch.setattr(f"{MODULE}.S3", lambda: None)


def _intent() -> QueryIntent:
    return QueryIntent(
        is_nonsense=True, record_type=None, columns=[], start_date=None, end_date=None
    )


def test_successful_query_mails_the_link(monkeypatch, ses) -> None:
    _stub_graph(
        monkeypatch,
        {"executed": ExecutedQuery(execution_id="abc", result_url=RESULT_URL)},
    )
    process.process_query(QUERY, EMAIL)

    (sent,) = ses.sent
    assert sent["to"] == EMAIL
    assert sent["subject"] == process.SUBJECT_READY
    assert RESULT_URL in sent["body"]


def test_invalid_query_mails_the_issues(monkeypatch, ses) -> None:
    _stub_graph(
        monkeypatch,
        {
            "executed": None,
            "validation": ValidationResult(
                valid=False, issues=[ValidationIssue.NONSENSE], intent=_intent()
            ),
        },
    )
    process.process_query(QUERY, EMAIL)

    (sent,) = ses.sent
    assert sent["subject"] == process.SUBJECT_INVALID
    assert ValidationIssue.NONSENSE.value in sent["body"]


def test_graph_error_mails_a_failure_notice(monkeypatch, ses) -> None:
    class ExplodingGraph:
        def invoke(self, _state):
            raise RuntimeError("Athena query FAILED")

    monkeypatch.setattr(f"{MODULE}.build_graph", lambda _athena, _s3: ExplodingGraph())
    monkeypatch.setattr(f"{MODULE}.Athena", lambda: None)
    monkeypatch.setattr(f"{MODULE}.S3", lambda: None)

    process.process_query(QUERY, EMAIL)

    (sent,) = ses.sent
    assert sent["subject"] == process.SUBJECT_FAILED


def test_unmailable_result_does_not_raise(monkeypatch) -> None:
    """A background task that dies leaves the user with no notice at all."""

    _stub_graph(
        monkeypatch,
        {"executed": ExecutedQuery(execution_id="abc", result_url=RESULT_URL)},
    )

    def explode() -> None:
        raise RuntimeError("SES_SENDER_EMAIL is unset")

    monkeypatch.setattr(f"{MODULE}._ses", explode)

    process.process_query(QUERY, EMAIL)
