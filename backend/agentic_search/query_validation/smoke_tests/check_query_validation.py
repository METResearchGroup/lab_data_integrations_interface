"""
Sanity check for validate_query() against gpt-5.4-nano.

Steps:
  1. Builds the table snapshot
  2. Extracts a QueryIntent for each case, printing what the model returned
  3. Asserts each case produces the expected issues

Requires OPENAI_API_KEY. Costs five nano calls.

Run from the project root:
  python -m backend.agentic_search.query_validation.smoke_tests.check_query_validation
"""

from __future__ import annotations

from backend.agentic_search.query_validation.models import ValidationIssue
from backend.agentic_search.query_validation.orchestrator import build_snapshot, validate_intent
from backend.agentic_search.query_validation.query_intent.extract import extract_intent

# One problem each, so a failure names exactly which check moved.
CASES: list[tuple[str, str, list[ValidationIssue]]] = [
    (
        "happy",
        "give me all the posts (text only) from the last week",
        [],
    ),
    (
        "nonsense",
        "asdfkaslekjf;k",
        [ValidationIssue.NONSENSE],
    ),
    (
        "missing table",
        "give me all of the profile names",
        [ValidationIssue.UNKNOWN_RECORD_TYPE],
    ),
    (
        "missing column",
        "give me the text and view counts of the posts from the last week",
        [ValidationIssue.UNKNOWN_COLUMN],
    ),
    (
        "missing row",
        "give me all the posts (text only) from March 2026",
        [ValidationIssue.RANGE_OUTSIDE_COVERAGE],
    ),
]


def main() -> None:
    print("--- table snapshot ---")
    snapshot = build_snapshot()
    for record_type, metadata in snapshot.items():
        print(f"  {record_type}: {metadata.coverage_start} to {metadata.coverage_end}")

    failures: list[str] = []

    for name, query, expected in CASES:
        print(f"\n--- {name} ---")
        print(f"  query: {query!r}")

        intent = extract_intent(query, snapshot)
        print(
            f"  intent: is_nonsense={intent.is_nonsense} record_type={intent.record_type} "
            f"columns={intent.columns} dates={intent.start_date}..{intent.end_date}"
        )

        result = validate_intent(intent, snapshot)
        print(f"  result: valid={result.valid} issues={[i.value for i in result.issues]}")

        if result.issues == expected:
            print("  PASS")
        else:
            failures.append(name)
            print(f"  FAIL: expected {[i.value for i in expected]}")

    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} passed")
    if failures:
        print(f"failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
