"""What the user receives once their query finishes. Runs in Lambda."""

from __future__ import annotations

import logging
import os

from backend.agentic_search.aws.ses import SES
from backend.agentic_search.query_validation.models import ValidationIssue

logger = logging.getLogger(__name__)

SENDER_VARIABLE = "SES_SENDER_EMAIL"

SUBJECT_READY = "Your query results are ready"
SUBJECT_INVALID = "Your query could not be run"
SUBJECT_FAILED = "Your query failed"


def _ses() -> SES:
    sender = os.getenv(SENDER_VARIABLE)
    if not sender:
        raise RuntimeError(f"{SENDER_VARIABLE} is unset, so results cannot be mailed")

    return SES(sender)


def _send(email: str, subject: str, body: str) -> None:
    """Mail failures are logged, not raised: there is nowhere left to report them."""

    try:
        _ses().send(to=email, subject=subject, body=body)
    except Exception:
        logger.exception("could not mail %s to %s", subject, email)


def mail_results(email: str, query: str, result_url: str) -> None:
    _send(
        email,
        SUBJECT_READY,
        f"Your query:\n\n  {query}\n\n"
        f"Download the results (link expires in 24 hours):\n\n  {result_url}\n",
    )


def mail_invalid(email: str, query: str, issues: list[ValidationIssue]) -> None:
    listed = "\n".join(f"  - {issue.value}" for issue in issues)
    _send(
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
