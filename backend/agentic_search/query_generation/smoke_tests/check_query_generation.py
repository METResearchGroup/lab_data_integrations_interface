"""
Prints the SQL generate_sql() builds for a few hand-written intents.

Deterministic and offline, so this is for reading the SQL rather than for
catching regressions — tests/backend/agentic_search/query_generation pins the
exact strings.

Run from the project root:
  python -m backend.agentic_search.query_generation.smoke_tests.check_query_generation
"""

from __future__ import annotations

from datetime import date

from backend.agentic_search.query_generation.generate import generate_sql
from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.constants import RecordType

# One axis each, so a surprise names which part of the clause list moved.
CASES: list[tuple[str, QueryIntent, str]] = [
    (
        "bounded range",
        QueryIntent(
            is_nonsense=False,
            record_type=RecordType.POSTS,
            columns=["uri", "text"],
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 20),
        ),
        "created_at < TIMESTAMP '2026-08-21 00:00:00'",
    ),
    (
        "open-ended start",
        QueryIntent(
            is_nonsense=False,
            record_type=RecordType.LIKES,
            columns=["subject_uri"],
            start_date=date(2026, 8, 20),
            end_date=None,
        ),
        "WHERE created_at >= TIMESTAMP '2026-08-20 00:00:00'",
    ),
    (
        "no dates, no columns",
        QueryIntent(
            is_nonsense=False,
            record_type=RecordType.FOLLOWS,
            columns=[],
            start_date=None,
            end_date=None,
        ),
        "SELECT *",
    ),
]


def main() -> None:
    failures: list[str] = []

    for name, intent, expected in CASES:
        print(f"--- {name} ---")
        print(
            f"  intent: record_type={intent.record_type} columns={intent.columns} "
            f"dates={intent.start_date}..{intent.end_date}"
        )

        generated = generate_sql(intent)
        for line in generated.sql.splitlines():
            print(f"    {line}")

        if expected in generated.sql:
            print("  PASS\n")
        else:
            failures.append(name)
            print(f"  FAIL: expected to find {expected!r}\n")

    print(f"{len(CASES) - len(failures)}/{len(CASES)} passed")
    if failures:
        print(f"failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
