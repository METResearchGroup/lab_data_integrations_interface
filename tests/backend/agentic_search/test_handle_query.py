"""handle_query's three outcomes, with the graph and Gmail stubbed out."""

from __future__ import annotations

import pytest
from opentelemetry.trace import StatusCode

from backend.agentic_search import handle_query as module
from backend.agentic_search import mail
from backend.agentic_search.query_execution.models import ExecutedQuery
from backend.agentic_search.query_validation.models import ValidationIssue, ValidationResult
from backend.agentic_search.query_validation.query_intent.models import QueryIntent

QUERY = "posts in July"
EMAIL = "someone@example.invalid"
RESULT_URL = "https://example.invalid/result.csv"


def _intent() -> QueryIntent:
    return QueryIntent(
        is_nonsense=True, record_type=None, columns=[], start_date=None, end_date=None
    )


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Capture at the Gmail boundary so the real body-building code still runs."""

    captured: list[dict[str, str]] = []

    class FakeGmail:
        def send(self, *, to: str, subject: str, body: str) -> None:
            captured.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr(mail, "_gmail", lambda: FakeGmail())
    return captured


def test_successful_query_mails_the_link(monkeypatch, sent) -> None:
    monkeypatch.setattr(
        module,
        "run_langgraph",
        lambda _query: (
            ValidationResult(valid=True, issues=[], intent=_intent()),
            None,
            ExecutedQuery(execution_id="abc", result_url=RESULT_URL),
        ),
    )
    module.handle_query(QUERY, EMAIL)

    (message,) = sent
    assert message["to"] == EMAIL
    assert message["subject"] == mail.SUBJECT_READY
    assert RESULT_URL in message["body"]


def test_invalid_query_mails_the_issues(monkeypatch, sent) -> None:
    monkeypatch.setattr(
        module,
        "run_langgraph",
        lambda _query: (
            ValidationResult(valid=False, issues=[ValidationIssue.NONSENSE], intent=_intent()),
            None,
            None,
        ),
    )
    module.handle_query(QUERY, EMAIL)

    (message,) = sent
    assert message["subject"] == mail.SUBJECT_INVALID
    assert ValidationIssue.NONSENSE.value in message["body"]


def test_postprocessing_rejection_mails_the_reason(monkeypatch, sent) -> None:
    """The query validated, so the reason has to come from the rejection, not the issues."""

    rejection = "estimated cost $9.00 is over the $1.00 limit"
    monkeypatch.setattr(
        module,
        "run_langgraph",
        lambda _query: (
            ValidationResult(valid=True, issues=[], intent=_intent()),
            rejection,
            None,
        ),
    )
    module.handle_query(QUERY, EMAIL)

    (message,) = sent
    assert message["subject"] == mail.SUBJECT_INVALID
    assert rejection in message["body"]


def test_graph_error_mails_a_failure_notice(monkeypatch, sent) -> None:
    def explode(_query):
        raise RuntimeError("Athena query FAILED")

    monkeypatch.setattr(module, "run_langgraph", explode)
    module.handle_query(QUERY, EMAIL)

    (message,) = sent
    assert message["subject"] == mail.SUBJECT_FAILED


def test_unmailable_result_does_not_raise(monkeypatch) -> None:
    """A background task that dies leaves the user with no notice at all."""

    monkeypatch.setattr(
        module,
        "run_langgraph",
        lambda _query: (
            ValidationResult(valid=True, issues=[], intent=_intent()),
            None,
            ExecutedQuery(execution_id="abc", result_url=RESULT_URL),
        ),
    )

    def no_sender():
        raise RuntimeError("GMAIL_SENDER_EMAIL is unset")

    monkeypatch.setattr(mail, "_gmail", no_sender)

    module.handle_query(QUERY, EMAIL)


def test_graph_error_is_recorded_on_the_run_span(monkeypatch, sent, spans) -> None:
    def explode(_query):
        raise RuntimeError("Athena query FAILED")

    monkeypatch.setattr(module, "run_langgraph", explode)
    module.handle_query(QUERY, EMAIL)

    by_name = {span.name: span for span in spans.get_finished_spans()}
    run = by_name["agentic_search.query"]
    assert run.attributes["outcome"] == "failed"
    assert run.status.status_code is StatusCode.ERROR
    assert by_name["mail"].parent.span_id == run.context.span_id


def test_unmailable_result_marks_the_mail_span_failed(monkeypatch, spans) -> None:
    """The one failure the user never hears about, so the trace must show it."""

    monkeypatch.setattr(
        module,
        "run_langgraph",
        lambda _query: (
            ValidationResult(valid=True, issues=[], intent=_intent()),
            None,
            ExecutedQuery(execution_id="abc", result_url=RESULT_URL),
        ),
    )

    def no_sender():
        raise RuntimeError("GMAIL_SENDER_EMAIL is unset")

    monkeypatch.setattr(mail, "_gmail", no_sender)
    module.handle_query(QUERY, EMAIL)

    by_name = {span.name: span for span in spans.get_finished_spans()}
    assert by_name["agentic_search.query"].attributes["outcome"] == "mail_failed"
    assert by_name["mail"].status.status_code is StatusCode.ERROR
