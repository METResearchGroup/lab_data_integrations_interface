"""
End-to-end check for mail.py: sends all three outcome emails for real.

Steps:
  1. Sends one message through Gmail directly, which raises on rejection
  2. Sends each of the three mail_* bodies, which swallow their own failures

Step 1 is what actually reports a bad sender or app password. The mail_*
helpers log and return, so a silent step 2 means step 1 already passed.

Hits real Gmail SMTP. Point MAIL_TEST_RECIPIENT at an address on another
provider: delivery to a stranger is the thing worth proving.

Run from the project root:
  python -m backend.agentic_search.smoke_tests.check_mail
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from backend.agentic_search.gmail import Gmail
from backend.agentic_search.mail import (
    PASSWORD_VARIABLE,
    SENDER_VARIABLE,
    mail_failure,
    mail_invalid,
    mail_results,
)
from backend.agentic_search.query_validation.models import ValidationIssue

QUERY = "give me all the posts (text only) from the last week"
RESULT_URL = "https://example.invalid/results.csv?X-Amz-Signature=smoke-test"
ISSUES = [ValidationIssue.UNKNOWN_COLUMN, ValidationIssue.RANGE_OUTSIDE_COVERAGE]


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    sender = os.getenv(SENDER_VARIABLE)
    if not sender:
        raise SystemExit(f"{SENDER_VARIABLE} is unset")

    password = os.getenv(PASSWORD_VARIABLE)
    if not password:
        raise SystemExit(f"{PASSWORD_VARIABLE} is unset")

    recipient = os.getenv("MAIL_TEST_RECIPIENT", sender)
    print(f"--- {sender} -> {recipient} ---")

    print("\n--- direct send ---")
    Gmail(sender, password).send(to=recipient, subject="Gmail smoke test", body="Direct send.\n")
    print("  accepted")

    print("\n--- outcome emails ---")
    mail_results(recipient, QUERY, RESULT_URL)
    print("  results")
    mail_invalid(recipient, QUERY, ISSUES)
    print("  invalid")
    mail_failure(recipient, QUERY)
    print("  failure")

    print(f"\n4 message(s) sent. Check {recipient} — including spam.")


if __name__ == "__main__":
    main()
