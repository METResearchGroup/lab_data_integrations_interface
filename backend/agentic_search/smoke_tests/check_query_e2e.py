"""
End-to-end check for the /query flow, minus the HTTP layer and auth.

Steps:
  1. Runs the graph on a valid query: validate -> generate -> execute
  2. Reads the first rows back off the presigned URL
  3. Mails the results, the same call the background task makes

Mirrors handle_query rather than calling it: that function swallows every
exception so the user always gets mail, which would hide a failure here.

Hits real Athena, real Gmail, and the real model. The week of posts is a paid
scan.

Run from the project root:
  python -m backend.agentic_search.smoke_tests.check_query_e2e
"""

from __future__ import annotations

import logging
import os
import urllib.request

from dotenv import load_dotenv

from backend.agentic_search.mail import SENDER_VARIABLE, mail_results
from backend.agentic_search.run_langgraph import run_langgraph

QUERY = "give me all the posts (text only) from the last week"
PREVIEW_ROWS = 5


def preview(url: str) -> list[str]:
    """The head of the result CSV, proving the presigned URL resolves."""

    with urllib.request.urlopen(url) as response:  # noqa: S310 — presigned https URL
        head = response.read(4096).decode("utf-8", errors="replace")
    return head.splitlines()[: PREVIEW_ROWS + 1]


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    sender = os.getenv(SENDER_VARIABLE)
    if not sender:
        raise SystemExit(f"{SENDER_VARIABLE} is unset")

    recipient = os.getenv("MAIL_TEST_RECIPIENT", sender)

    print("--- query ---")
    print(f"  {QUERY!r}")

    print("\n--- running graph ---")
    validation, executed = run_langgraph(QUERY)

    intent = validation.intent
    print(
        f"  intent: record_type={intent.record_type} columns={intent.columns} "
        f"dates={intent.start_date}..{intent.end_date}"
    )
    print(f"  valid={validation.valid} issues={[i.value for i in validation.issues]}")

    if executed is None:
        raise SystemExit(
            f"expected a valid query, but it was rejected: {[i.value for i in validation.issues]}"
        )

    print(f"  execution_id: {executed.execution_id}")
    print(f"  result_url: {executed.result_url[:100]}...")

    print("\n--- result csv ---")
    lines = preview(executed.result_url)
    for line in lines:
        print(f"  {line}")

    # The header row is always written, so anything past it is real data.
    rows = max(len(lines) - 1, 0)
    print(f"\n{rows} row(s) previewed")
    if rows == 0:
        raise SystemExit("the query returned no rows, so there is nothing to mail")

    print("\n--- mailing ---")
    mail_results(recipient, QUERY, executed.result_url)
    print(f"  sent to {recipient} — check spam too")


if __name__ == "__main__":
    main()
