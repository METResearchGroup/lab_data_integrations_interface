"""The endpoint's background task: run the graph, then mail whatever came back."""

from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.trace import StatusCode

from backend.agentic_search.mail import mail_failure, mail_invalid, mail_results
from backend.agentic_search.run_langgraph import run_langgraph

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


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

        if executed is None:
            span.set_attribute("outcome", "rejected" if rejection else "invalid")
            reasons = [rejection] if rejection else [issue.value for issue in validation.issues]
            mail_invalid(email, query, reasons)
            return

        span.set_attribute("outcome", "results")
        mail_results(email, query, executed.result_url)
