"""
Sanity check for the two postprocessing checks against the real posts table.

Steps:
  1. Runs is_select_only over reads and writes, starting with real generated SQL
  2. Estimates the scan for four intents against the live Iceberg metadata
  3. Asserts the estimate shrinks as the query narrows

Reads Glue and S3 metadata only. No Athena query runs, so nothing is billed for
a scan. Needs credentials for us-east-2.

Run from the project root:
  python -m backend.agentic_search.query_postprocessing.smoke_tests.check_query_postprocessing
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.agentic_search.query_generation.generate import generate_sql
from backend.agentic_search.query_postprocessing.check_scan_cost import (
    BYTES_PER_GB,
    MAX_SCAN_BYTES,
    estimate_scan_bytes,
    over_scan_limit,
)
from backend.agentic_search.query_postprocessing.check_select_only import is_select_only
from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.aws.catalog import build_catalog
from bluesky_ingestion_jetstream.aws.constants import GLUE_DATABASE
from bluesky_ingestion_jetstream.constants import RecordType

# The most recent partition that is certain to be closed.
YESTERDAY = date.today() - timedelta(days=1)
LAST_MONTH = YESTERDAY - timedelta(days=30)


def _intent(columns: list[str], start_date: date | None, end_date: date | None) -> QueryIntent:
    return QueryIntent(
        is_nonsense=False,
        record_type=RecordType.POSTS,
        columns=columns,
        start_date=start_date,
        end_date=end_date,
    )


GENERATED = generate_sql(_intent(["text"], YESTERDAY, YESTERDAY))

# name -> (sql, is a read)
SQL_CASES: list[tuple[str, str, bool]] = [
    ("generated", GENERATED.sql, True),
    ("delete", "DELETE FROM bluesky_raw.posts", False),
    ("insert", "INSERT INTO bluesky_raw.posts SELECT * FROM bluesky_raw.posts", False),
    ("drop", "DROP TABLE bluesky_raw.posts", False),
    ("optimize", "OPTIMIZE bluesky_raw.posts REWRITE DATA USING BIN_PACK", False),
    ("stacked write", "SELECT 1; DROP TABLE bluesky_raw.posts", False),
]

# Ordered widest last: each estimate has to be at least the one before it.
SCAN_CASES: list[tuple[str, QueryIntent]] = [
    ("one day, text only", _intent(["text"], YESTERDAY, YESTERDAY)),
    ("one day, every column", _intent([], YESTERDAY, YESTERDAY)),
    ("30 days, every column", _intent([], LAST_MONTH, YESTERDAY)),
    ("whole table, every column", _intent([], None, None)),
]


def check_sql() -> list[str]:
    failures = []

    for name, sql, expected in SQL_CASES:
        allowed = is_select_only(sql)
        verdict = "PASS" if allowed == expected else "FAIL"
        if verdict == "FAIL":
            failures.append(name)
        print(f"  {verdict}  {name}: allowed={allowed} (expected {expected})")

    return failures


def check_scans() -> list[str]:
    table = build_catalog().load_table((GLUE_DATABASE, RecordType.POSTS))
    print(f"  snapshot: {table.metadata.current_snapshot_id}")

    failures = []
    previous_bytes = 0
    previous_name = "nothing"

    for name, intent in SCAN_CASES:
        scan_bytes = estimate_scan_bytes(table, intent)
        rejection = over_scan_limit(table, intent)
        state = "over the cap" if rejection else "allowed"
        print(f"  {name}: {scan_bytes / BYTES_PER_GB:.2f} GB ({state})")

        # Widening a query cannot scan less than narrowing it did.
        if scan_bytes < previous_bytes:
            failures.append(name)
            print(f"    FAIL: scans less than {previous_name}")

        previous_bytes, previous_name = scan_bytes, name

    return failures


def main() -> None:
    print("--- generated sql ---")
    for line in GENERATED.sql.splitlines():
        print(f"  {line}")

    print("\n--- select only ---")
    failures = check_sql()

    print(f"\n--- scan estimates (cap {MAX_SCAN_BYTES / BYTES_PER_GB:.0f} GB) ---")
    failures += check_scans()

    total = len(SQL_CASES) + len(SCAN_CASES)
    print(f"\n{total - len(failures)}/{total} passed")
    if failures:
        raise SystemExit(f"failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
