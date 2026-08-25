"""
End-to-end check for execute_query(): post text from 2026-08-10.

Steps:
  1. Runs a hand-written query on Athena, blocking until it finishes
  2. Presigns the result file and reads the first rows back over HTTP

The SQL is literal so a failure here is execution's, not generation's.

Hits real AWS. Needs credentials for us-east-2.

Run from the project root:
  python -m backend.agentic_search.query_execution.smoke_tests.check_query_execution
"""

from __future__ import annotations

import urllib.request

from backend.agentic_search.query_execution.execute import execute_query
from backend.agentic_search.query_generation.models import GeneratedQuery
from bluesky_ingestion_jetstream.constants import RecordType

PREVIEW_ROWS = 5

GENERATED = GeneratedQuery(
    sql=(
        'SELECT "text"\n'
        "FROM bluesky_raw.posts\n"
        "WHERE created_at >= TIMESTAMP '2026-08-10 00:00:00' "
        "AND created_at < TIMESTAMP '2026-08-11 00:00:00'\n"
        f"LIMIT {PREVIEW_ROWS}"
    ),
    record_type=RecordType.POSTS,
)


def preview(url: str) -> list[str]:
    """The head of the result CSV, proving the presigned URL resolves."""

    with urllib.request.urlopen(url) as response:  # noqa: S310 — presigned https URL
        head = response.read(4096).decode("utf-8", errors="replace")
    return head.splitlines()[: PREVIEW_ROWS + 1]


def main() -> None:
    print("--- sql ---")
    for line in GENERATED.sql.splitlines():
        print(f"  {line}")

    print("\n--- running ---")
    executed = execute_query(GENERATED)
    print(f"  execution_id: {executed.execution_id}")
    print(f"  result_url: {executed.result_url[:100]}...")

    print("\n--- result csv ---")
    lines = preview(executed.result_url)
    for line in lines:
        print(f"  {line}")

    # The header row is always written, so anything past it is real data.
    print(f"\n{max(len(lines) - 1, 0)} row(s) returned")


if __name__ == "__main__":
    main()
