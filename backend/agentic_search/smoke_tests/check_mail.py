"""
End-to-end check for mail.py: sends all three outcome emails for real.

Steps:
  1. Sends one message through SES directly, which raises on rejection
  2. Sends each of the three mail_* bodies, which swallow their own failures

Step 1 is what actually reports a bad sender, region, or IAM permission. The
mail_* helpers log and return, so a silent step 2 means step 1 already passed.

Hits real SES in us-east-2. The recipient must be a verified identity while the
account is in the sandbox.

Run from the project root:
  python -m backend.agentic_search.smoke_tests.check_mail
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from backend.agentic_search.aws.ses import SES
from backend.agentic_search.mail import (
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

    # Sandbox delivers only to verified identities, so the sender is the one
    # address guaranteed to be verified.
    recipient = os.getenv("SES_TEST_RECIPIENT", sender)
    print(f"--- {sender} -> {recipient} ---")

    print("\n--- direct send ---")
    SES(sender).send(to=recipient, subject="SES smoke test", body="Direct send.\n")
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
