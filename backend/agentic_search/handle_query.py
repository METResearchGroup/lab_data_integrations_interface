"""The endpoint's background task: run the graph, then mail whatever came back."""

from __future__ import annotations

import logging
import time

from opentelemetry import trace
from opentelemetry.trace import StatusCode

from backend.agentic_search.mail import (
    mail_demo_results,
    mail_failure,
    mail_invalid,
    mail_results,
)
from backend.agentic_search.run_langgraph import run_langgraph
from backend.demo.queries import DELAY_SECONDS, match_demo_query

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def handle_query(query: str, email: str) -> None:
    with tracer.start_as_current_span("agentic_search.query") as span:
        span.set_attribute("query", query)

        demo = match_demo_query(query)
        if demo is not None:
            time.sleep(DELAY_SECONDS)
            sent = mail_demo_results(email, query, demo.summary, demo.csv)
            span.set_attribute("outcome", "demo" if sent else "mail_failed")
            return

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
            outcome = "rejected" if rejection else "invalid"
            reasons = [rejection] if rejection else [issue.value for issue in validation.issues]
            sent = mail_invalid(email, query, reasons)
        else:
            outcome = "results"
            sent = mail_results(email, query, executed.result_url)

        span.set_attribute("outcome", outcome if sent else "mail_failed")
