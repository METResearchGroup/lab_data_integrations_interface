"""The endpoint's background task: run the graph, then mail whatever came back."""

from __future__ import annotations

import logging

from backend.agentic_search.mail import mail_failure, mail_invalid, mail_results
from backend.agentic_search.run_langgraph import run_langgraph

logger = logging.getLogger(__name__)


def handle_query(query: str, email: str) -> None:
    try:
        validation, executed = run_langgraph(query)
    except Exception:
        logger.exception("query failed for %s", email)
        mail_failure(email, query)
        return

    if executed is None:
        mail_invalid(email, query, validation.issues)
        return

    mail_results(email, query, executed.result_url)
