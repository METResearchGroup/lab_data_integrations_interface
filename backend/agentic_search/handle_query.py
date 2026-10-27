"""The endpoint's background task: run the graph, then mail whatever came back."""

from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.trace import StatusCode

from backend.agentic_search.mail import mail_failure, mail_invalid, mail_results
from backend.agentic_search.query_validation.models import ValidationResult
from backend.agentic_search.query_validation.query_intent.dates import START_LOOKBACK_DAYS
from backend.agentic_search.run_langgraph import run_langgraph

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def _date_note(validation: ValidationResult | None) -> str:
    """Tell the researcher which date sides the program filled in."""

    intent = None if validation is None else validation.intent
    if intent is None:
        return ""
    lines = []
    if intent.start_date_inferred and intent.start_date is not None:
        lines.append(
            f"Start date {intent.start_date.isoformat()} is {START_LOOKBACK_DAYS} days "
            "before the end, because the question stated no start."
        )
    if intent.end_date_inferred and intent.end_date is not None:
        lines.append(
            f"End date {intent.end_date.isoformat()} is the current UTC date, "
            "because the question stated no end."
        )
    if not lines:
        return ""
    return " ".join(lines) + "\n\n"


def handle_query(query: str, email: str) -> None:
    with tracer.start_as_current_span("agentic_search.query") as span:
        span.set_attribute("query", query)

        try:
            validation, rejection, executed = run_langgraph(query)
        except Exception as error:
            logger.exception("query failed for %s", email)
            span.record_exception(error)
            span.set_status(StatusCode.ERROR)
            span.set_attribute("outcome", "failed")
            mail_failure(email, query)
            return

        note = _date_note(validation)
        if executed is None:
            outcome = "rejected" if rejection else "invalid"
            reasons = [rejection] if rejection else [issue.value for issue in validation.issues]
            sent = mail_invalid(email, query, reasons, note=note)
        else:
            outcome = "results"
            sent = mail_results(email, query, executed.result_url, note=note)

        span.set_attribute("outcome", outcome if sent else "mail_failed")
