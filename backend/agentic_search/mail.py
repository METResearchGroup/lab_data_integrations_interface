"""What the user receives once their query finishes. Runs in a background task."""

from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.trace import StatusCode

from backend.agentic_search.gmail import Gmail

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

SENDER_VARIABLE = "GMAIL_SENDER_EMAIL"
PASSWORD_VARIABLE = "GMAIL_APP_PASSWORD"

SUBJECT_READY = "Your query results are ready"
SUBJECT_INVALID = "Your query could not be run"
SUBJECT_FAILED = "Your query failed"


def _gmail() -> Gmail:
    sender = os.getenv(SENDER_VARIABLE)
    if not sender:
        raise RuntimeError(f"{SENDER_VARIABLE} is unset, so results cannot be mailed")

    # Google displays app passwords in four spaced groups; SMTP wants the 16 raw chars.
    password = "".join(os.getenv(PASSWORD_VARIABLE, "").split())
    if not password:
        raise RuntimeError(f"{PASSWORD_VARIABLE} is unset, so results cannot be mailed")

    return Gmail(sender, password)


def _send(email: str, subject: str, body: str) -> bool:
    """Mail failures are logged, not raised: there is nowhere left to report them."""

    with tracer.start_as_current_span("mail") as span:
        span.set_attribute("subject", subject)
        try:
            _gmail().send(to=email, subject=subject, body=body)
        except Exception as error:
            logger.exception("could not mail %s to %s", subject, email)
            span.record_exception(error)
            span.set_status(StatusCode.ERROR)
            return False
        return True


def mail_results(email: str, query: str, result_url: str) -> bool:
    return _send(
        email,
        SUBJECT_READY,
        f"Your query:\n\n  {query}\n\n"
        f"Download the results (link expires in 24 hours):\n\n  {result_url}\n",
    )


def mail_invalid(email: str, query: str, issues: list[str]) -> bool:
    listed = "\n".join(f"  - {issue}" for issue in issues)
    return _send(
        email,
        SUBJECT_INVALID,
        f"Your query:\n\n  {query}\n\nIt could not be run:\n\n{listed}\n",
    )


def mail_failure(email: str, query: str) -> None:
    _send(
        email,
        SUBJECT_FAILED,
        f"Your query:\n\n  {query}\n\nIt hit an error and did not finish.\n",
    )
