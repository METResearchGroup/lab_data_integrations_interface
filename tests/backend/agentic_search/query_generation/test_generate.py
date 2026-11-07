"""generate_sql over the intent shapes validation lets through."""

from __future__ import annotations

from datetime import date

import pytest

from backend.agentic_search.query_generation.generate import generate_sql
from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.constants import RecordType


def make_intent(
    record_type: RecordType | None = RecordType.POSTS,
    columns: list[str] | None = None,
    start_date: date | None = date(2026, 7, 1),
    end_date: date | None = date(2026, 7, 31),
) -> QueryIntent:
    return QueryIntent(
        is_nonsense=False,
        record_type=record_type,
        columns=["uri", "text"] if columns is None else columns,
        start_date=start_date,
        end_date=end_date,
    )


def test_full_query() -> None:
    result = generate_sql(make_intent())

    assert result.record_type is RecordType.POSTS
    assert result.sql == (
        'SELECT "uri", "text"\n'
        "FROM bluesky_raw.posts\n"
        "WHERE created_at >= TIMESTAMP '2026-07-01 00:00:00' "
        "AND created_at < TIMESTAMP '2026-08-01 00:00:00'\n"
        "ORDER BY created_at"
    )


def test_no_columns_selects_star() -> None:
    assert "SELECT *" in generate_sql(make_intent(columns=[])).sql


def test_end_date_upper_bound_is_the_next_midnight() -> None:
    sql = generate_sql(make_intent(end_date=date(2026, 7, 31))).sql

    # Half-open, so rows stamped later on the 31st still land inside the range.
    assert "created_at < TIMESTAMP '2026-08-01 00:00:00'" in sql


@pytest.mark.parametrize(
    ("start_date", "end_date", "expected"),
    [
        (None, date(2026, 7, 31), "WHERE created_at < TIMESTAMP '2026-08-01 00:00:00'"),
        (date(2026, 7, 1), None, "WHERE created_at >= TIMESTAMP '2026-07-01 00:00:00'"),
    ],
)
def test_one_sided_range(start_date: date | None, end_date: date | None, expected: str) -> None:
    assert expected in generate_sql(make_intent(start_date=start_date, end_date=end_date)).sql


def test_unbounded_range_has_no_where_clause() -> None:
    assert "WHERE" not in generate_sql(make_intent(start_date=None, end_date=None)).sql


def test_no_limit_clause() -> None:
    """A LIMIT caps rows, not bytes scanned, so the scan check replaced it."""

    assert "LIMIT" not in generate_sql(make_intent()).sql


def test_column_quotes_are_escaped() -> None:
    assert 'SELECT "we""ird"' in generate_sql(make_intent(columns=['we"ird'])).sql


def test_missing_record_type_raises() -> None:
    with pytest.raises(ValueError, match="record type"):
        generate_sql(make_intent(record_type=None))


def _keyword_sql(keywords: list[str], match: str = "any") -> str:
    intent = make_intent().model_copy(update={"keywords": keywords, "match": match})
    return generate_sql(intent).sql


def test_star_term_becomes_a_substring() -> None:
    sql = _keyword_sql(["palestin*", "israel*"], match="all")

    assert """regexp_like("text", '(?i)palestin') AND regexp_like("text", '(?i)israel')""" in sql
    assert r"\*" not in sql.split("WHERE")[1]


def test_leading_star_is_removed() -> None:
    assert """regexp_like("text", '(?i)palestin')""" in _keyword_sql(["*palestin*"])


def test_term_without_star_keeps_word_boundaries() -> None:
    assert r"(?i)(?:palestin|\bgaza\b)" in _keyword_sql(["palestin*", "gaza"])


def test_inner_star_stays_literal() -> None:
    assert r"\ba\*b\b" in _keyword_sql(["a*b"])


def test_only_stars_is_refused() -> None:
    with pytest.raises(ValueError, match="empty"):
        _keyword_sql(["**"])
