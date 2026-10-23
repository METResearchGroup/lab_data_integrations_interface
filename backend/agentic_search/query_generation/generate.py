"""Turns a validated QueryIntent into Athena SQL.

Keyword filters are built here. The model never writes them. `any` is one
case-insensitive alternation. `all` is a separate predicate per term, AND-ed.
`matched_keywords` records the first term that hit, the same shape as the
name-match CASE in the September 2026 client export.
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.agentic_search.query_generation.models import GeneratedQuery
from backend.agentic_search.query_validation.query_intent.models import (
    MAX_KEYWORD_LENGTH,
    MAX_KEYWORDS,
    TEXT_COLUMN,
    KeywordMatch,
    QueryIntent,
)
from bluesky_ingestion_jetstream.aws.constants import GLUE_DATABASE, PARTITION_SOURCE_COLUMN
from bluesky_ingestion_jetstream.constants import RecordType

# RE2 metacharacters. Python's re.escape also backslashes spaces and "#",
# and RE2 rejects "\ " as an unknown escape, so a phrase would not compile.
_RE2_METACHARACTERS = set(r"\^$.|?*+()[]{}")


def _quote(identifier: str) -> str:
    return '"{}"'.format(identifier.replace('"', '""'))


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _escape_regex(term: str) -> str:
    return "".join(f"\\{char}" if char in _RE2_METACHARACTERS else char for char in term)


def _term_body(term: str, *, whole_word: bool) -> str:
    escaped = _escape_regex(term)
    if whole_word:
        return rf"\b{escaped}\b"
    return escaped


def _term_pattern(term: str, *, whole_word: bool) -> str:
    return f"(?i){_term_body(term, whole_word=whole_word)}"


def _any_pattern(terms: list[str], *, whole_word: bool) -> str:
    bodies = [_term_body(term, whole_word=whole_word) for term in terms]
    if len(bodies) == 1:
        return f"(?i){bodies[0]}"
    return "(?i)(?:" + "|".join(bodies) + ")"


def _regexp_like(pattern: str) -> str:
    return f"regexp_like({_quote(TEXT_COLUMN)}, {_sql_string(pattern)})"


def _usable_keywords(keywords: list[str]) -> list[str]:
    """The terms that will be embedded. Raises when validation was bypassed."""

    terms = [keyword.strip() for keyword in keywords]
    if not terms:
        return []
    if len(terms) > MAX_KEYWORDS:
        raise ValueError(f"at most {MAX_KEYWORDS} keywords")
    for term in terms:
        if not term:
            raise ValueError("keyword is empty")
        if len(term) > MAX_KEYWORD_LENGTH:
            raise ValueError(f"keyword longer than {MAX_KEYWORD_LENGTH} characters")
    return terms


def _keyword_condition(terms: list[str], match: KeywordMatch, *, whole_word: bool) -> str:
    if match == "all":
        predicates = [_regexp_like(_term_pattern(term, whole_word=whole_word)) for term in terms]
        return " AND ".join(predicates)
    return _regexp_like(_any_pattern(terms, whole_word=whole_word))


def _matched_keywords_expr(terms: list[str], *, whole_word: bool) -> str:
    branches = [
        f"WHEN {_regexp_like(_term_pattern(term, whole_word=whole_word))} THEN {_sql_string(term)}"
        for term in terms
    ]
    return "CASE\n    " + "\n    ".join(branches) + f"\n  END AS {_quote('matched_keywords')}"


def _select_clause(columns: list[str], matched: str | None) -> str:
    selection = ", ".join(_quote(column) for column in columns) if columns else "*"
    if matched is None:
        return f"SELECT {selection}"
    return f"SELECT {selection},\n  {matched}"


def _from_clause(table: str) -> str:
    return f"FROM {table}"


def _timestamp(day: date) -> str:
    return f"TIMESTAMP '{day} 00:00:00'"


def _where_clause(
    start_date: date | None,
    end_date: date | None,
    terms: list[str],
    match: KeywordMatch,
    *,
    whole_word: bool,
) -> str:
    conditions = []
    if start_date is not None:
        conditions.append(f"{PARTITION_SOURCE_COLUMN} >= {_timestamp(start_date)}")
    if end_date is not None:
        conditions.append(f"{PARTITION_SOURCE_COLUMN} < {_timestamp(end_date + timedelta(days=1))}")
    if terms:
        conditions.append(_keyword_condition(terms, match, whole_word=whole_word))

    return f"WHERE {' AND '.join(conditions)}" if conditions else ""


def _order_by_clause() -> str:
    return f"ORDER BY {PARTITION_SOURCE_COLUMN}"


def generate_sql(intent: QueryIntent) -> GeneratedQuery:
    """Assumes the intent already passed validation.

    No LIMIT: it caps rows returned, not bytes scanned, so it never made the
    query cheaper. Postprocessing caps the scan itself.
    """

    if intent.record_type is None:
        raise ValueError("intent has no record type")

    terms = _usable_keywords(intent.keywords)
    if terms and intent.record_type is not RecordType.POSTS:
        raise ValueError("keywords require posts")

    matched = _matched_keywords_expr(terms, whole_word=intent.whole_word) if terms else None
    table = f"{GLUE_DATABASE}.{intent.record_type.value}"
    clauses = [
        _select_clause(intent.columns, matched),
        _from_clause(table),
        _where_clause(
            intent.start_date,
            intent.end_date,
            terms,
            intent.match,
            whole_word=intent.whole_word,
        ),
        _order_by_clause(),
    ]

    return GeneratedQuery(
        sql="\n".join(clause for clause in clauses if clause),
        record_type=intent.record_type,
    )
