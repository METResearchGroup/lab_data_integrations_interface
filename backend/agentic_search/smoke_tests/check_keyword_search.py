"""
Prints the SQL extract_intent + generate_sql produce for a few keyword questions.
When AWS credentials are present, counts rows for the keyword "the" over one
closed day and measures that day's text column against the 10 GB cap.

Needs OPENAI_API_KEY for the extraction half. The Athena half needs credentials
for us-east-2. It runs only when the day's estimated scan is at most 15 GB.

Run from the project root:
  python -m backend.agentic_search.smoke_tests.check_keyword_search
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import boto3
from dotenv import load_dotenv

from backend.agentic_search.query_execution.execute import WORKGROUP
from backend.agentic_search.query_generation.generate import generate_sql
from backend.agentic_search.query_postprocessing.check_scan_cost import (
    BYTES_PER_GB,
    MAX_SCAN_BYTES,
    estimate_scan_bytes,
)
from backend.agentic_search.query_validation.models import TableMetadata
from backend.agentic_search.query_validation.orchestrator import build_snapshot
from backend.agentic_search.query_validation.query_intent.extract import extract_intent
from backend.agentic_search.query_validation.query_intent.models import (
    TEXT_COLUMN,
    QueryIntent,
)
from bluesky_ingestion_jetstream.aws.catalog import build_catalog
from bluesky_ingestion_jetstream.aws.constants import GLUE_DATABASE, PARTITION_SOURCE_COLUMN
from bluesky_ingestion_jetstream.constants import RecordType
from lib.aws.athena import Athena

# A one-day keyword scan above this is no longer the small check this script runs.
SMALL_SCAN_BYTES = 15 * BYTES_PER_GB
COMMON_KEYWORD = "the"
DAY_LOOKBACK = 21

# name, question, terms that should show up in the SQL, whether a filter is expected
QUESTIONS: list[tuple[str, str, tuple[str, ...], bool]] = [
    (
        "single keyword",
        "Show the text of posts from 2026-08-15 that say climate.",
        ("climate",),
        True,
    ),
    (
        "any of several",
        "Show the text of posts from 2026-08-15 through 2026-08-16 that mention trump or biden.",
        ("trump", "biden"),
        True,
    ),
    (
        "all of several",
        "Show the text of posts from 2026-08-15 that mention both climate and policy.",
        ("climate", "policy"),
        True,
    ),
    (
        "phrase",
        'Show the text of posts from 2026-08-15 with the phrase "climate change".',
        ("climate change",),
        True,
    ),
    (
        "hashtag",
        "Show the text of posts from 2026-08-15 tagged #climate.",
        ("#climate",),
        True,
    ),
    (
        "no keyword filter",
        "Posts from 2026-08-15 with their text and language.",
        (),
        False,
    ),
]


def _safe_error(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if any(token in lowered for token in ("akia", "secret", "aws_access_key", "token", "password")):
        return f"{type(exc).__name__} (details redacted)"
    return f"{type(exc).__name__}: {text}"


def _aws_ready() -> bool:
    return boto3.Session().get_credentials() is not None


def _print_intent(intent: QueryIntent) -> None:
    print(
        f"  intent: record_type={intent.record_type} columns={intent.columns} "
        f"keywords={intent.keywords} match={intent.match} "
        f"whole_word={intent.whole_word} dates={intent.start_date}..{intent.end_date}"
    )


def _print_sql(sql: str) -> None:
    print("  sql:")
    for line in sql.splitlines():
        print(f"    {line}")


def _sql_matches(
    sql: str,
    intent: QueryIntent,
    terms: tuple[str, ...],
    expect_filter: bool,
) -> bool:
    lowered = sql.lower()
    if expect_filter:
        missing = [term for term in terms if term.lower() not in lowered]
        return "regexp_like" in lowered and not missing and bool(intent.keywords)
    return "regexp_like" not in lowered and not intent.keywords


def _one_question(
    name: str,
    question: str,
    terms: tuple[str, ...],
    expect_filter: bool,
    snapshot: dict[RecordType, TableMetadata],
) -> bool:
    print(f"\n--- {name} ---")
    print(f"  question: {question}")
    try:
        intent = extract_intent(question, snapshot)
    except Exception as exc:
        print(f"  FAIL extract: {_safe_error(exc)}")
        return False

    _print_intent(intent)
    if intent.record_type is None:
        print("  FAIL: no record type, so no SQL")
        return False

    try:
        sql = generate_sql(intent).sql
    except Exception as exc:
        print(f"  FAIL generate: {_safe_error(exc)}")
        return False

    _print_sql(sql)
    if _sql_matches(sql, intent, terms, expect_filter):
        print("  PASS")
        return True
    expected = f"regexp_like and terms {terms}" if expect_filter else "no keyword filter"
    print(f"  FAIL: expected {expected}")
    return False


def check_extraction() -> list[str]:
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is unset; skipped extract + generate.")
        return []

    snapshot = build_snapshot()
    failures = []
    for name, question, terms, expect_filter in QUESTIONS:
        if not _one_question(name, question, terms, expect_filter, snapshot):
            failures.append(name)
    return failures


def _day_intent(day: date) -> QueryIntent:
    return QueryIntent(
        is_nonsense=False,
        record_type=RecordType.POSTS,
        columns=[TEXT_COLUMN],
        start_date=day,
        end_date=day,
        keywords=[COMMON_KEYWORD],
        match="any",
        whole_word=True,
    )


def _row_filter(day: date) -> str:
    end = day + timedelta(days=1)
    return (
        f"{PARTITION_SOURCE_COLUMN} >= '{day.isoformat()}T00:00:00+00:00' "
        f"AND {PARTITION_SOURCE_COLUMN} < '{end.isoformat()}T00:00:00+00:00'"
    )


def _column_bytes(table, day: date, column: str) -> int | None:
    """Sum one leaf column's on-disk size. None when a file omits the size."""

    field_id = table.schema().find_field(column).field_id
    total = 0
    for task in table.scan(row_filter=_row_filter(day)).plan_files():
        sizes = task.file.column_sizes or {}
        if field_id not in sizes:
            return None
        total += sizes[field_id]
    return total


def _latest_day_with_data(table) -> tuple[date, int] | None:
    today = date.today()
    for offset in range(2, DAY_LOOKBACK + 1):
        day = today - timedelta(days=offset)
        scan_bytes = estimate_scan_bytes(table, _day_intent(day))
        if scan_bytes > 0:
            return day, scan_bytes
    return None


def _count_sql(day: date) -> str:
    generated = generate_sql(_day_intent(day))
    where = generated.sql.split("\nWHERE ", 1)[1].split("\nORDER BY ", 1)[0]
    table = f"{GLUE_DATABASE}.{RecordType.POSTS.value}"
    return f"SELECT count(*) AS row_count\nFROM {table}\nWHERE {where}"


def _run_count(sql: str) -> tuple[int, int]:
    athena = Athena()
    execution_id = athena.run_query(sql, database=GLUE_DATABASE, workgroup=WORKGROUP)
    execution = athena.client.get_query_execution(QueryExecutionId=execution_id)["QueryExecution"]
    scanned = int(execution["Statistics"]["DataScannedInBytes"])
    result = athena.client.get_query_results(QueryExecutionId=execution_id, MaxResults=2)
    value = result["ResultSet"]["Rows"][1]["Data"][0]["VarCharValue"]
    print(f"  execution_id: {execution_id}")
    return int(value), scanned


def check_live_scan() -> list[str]:
    print("\n--- live scan ---")
    if not _aws_ready():
        print("  no AWS credentials; skipped Iceberg measurement and Athena.")
        return []

    try:
        table = build_catalog().load_table((GLUE_DATABASE, RecordType.POSTS.value))
    except Exception as exc:
        print(f"  FAIL catalog: {_safe_error(exc)}")
        return ["catalog"]

    found = _latest_day_with_data(table)
    if found is None:
        print(f"  no post files in the last {DAY_LOOKBACK} closed days")
        return ["no-day"]

    day, scan_bytes = found
    text_bytes = _column_bytes(table, day, TEXT_COLUMN)
    created_bytes = _column_bytes(table, day, PARTITION_SOURCE_COLUMN)
    print(f"  day: {day.isoformat()}")
    print(
        f"  estimated keyword scan (text + created_at): "
        f"{scan_bytes} bytes ({scan_bytes / BYTES_PER_GB:.3f} GB)"
    )
    cap_gb = MAX_SCAN_BYTES / BYTES_PER_GB
    if text_bytes is None:
        print("  text column size: unavailable (a file omitted column_sizes)")
    else:
        print(f"  text column: {text_bytes} bytes ({text_bytes / BYTES_PER_GB:.3f} GB)")
        if text_bytes:
            text_days = MAX_SCAN_BYTES / text_bytes
            print(f"  days of text alone under the {cap_gb:.0f} GB cap: {text_days:.1f}")
    if created_bytes is None:
        print("  created_at column size: unavailable (a file omitted column_sizes)")
    else:
        print(f"  created_at column: {created_bytes} bytes ({created_bytes / BYTES_PER_GB:.3f} GB)")

    if scan_bytes:
        days = MAX_SCAN_BYTES / scan_bytes
        print(f"  days of text + created_at under the {cap_gb:.0f} GB cap: {days:.1f}")
        print("  selecting more columns than text shortens that. SELECT * reads the whole file.")

    if scan_bytes > SMALL_SCAN_BYTES:
        print(
            f"  skipped Athena: the day estimates above "
            f"{SMALL_SCAN_BYTES / BYTES_PER_GB:.0f} GB, so it is not a small check"
        )
        return []

    sql = _count_sql(day)
    print("  athena count sql:")
    for line in sql.splitlines():
        print(f"    {line}")
    try:
        rows, scanned = _run_count(sql)
    except Exception as exc:
        print(f"  FAIL athena: {_safe_error(exc)}")
        return ["athena"]

    print(f"  rows: {rows}")
    print(f"  bytes scanned: {scanned} ({scanned / BYTES_PER_GB:.3f} GB)")
    return []


def main() -> None:
    load_dotenv()
    print("--- extract + generate ---")
    failures = check_extraction()
    failures += check_live_scan()
    if failures:
        raise SystemExit(f"failed: {', '.join(failures)}")
    print("\ndone")


if __name__ == "__main__":
    main()
