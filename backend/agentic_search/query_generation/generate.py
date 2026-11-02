"""Turns a validated QueryIntent into Athena SQL."""

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

# Athena's regexp_like uses RE2, the regular-expression library Trino ships.
# These characters are RE2 operators. A backslash in front of each one makes
# it match literally. Python's re.escape also backslashes spaces and "#", and
# RE2 rejects "\ " as an unknown escape, so a phrase would not compile. This
# set is the operator list we escape, and nothing else.
_RE2_METACHARACTERS = set(r"\^$.|?*+()[]{}")


def _quote(identifier: str) -> str:
    return '"{}"'.format(identifier.replace('"', '""'))


def _sql_string(value: str) -> str:
    """Quote ``value`` as an Athena string literal.

    A single quote inside ``value`` is doubled, which is how SQL writes one quote.

    Examples
    --------
    ``O'Brien`` becomes ``'O''Brien'``.
    """

    return "'" + value.replace("'", "''") + "'"


def _escape_regex(term: str) -> str:
    """Escape RE2 operators in ``term`` so they match as typed characters.

    Spaces, ``#``, ``@``, and quotes are left as typed.

    Examples
    --------
    ``a.b+c?`` becomes ``a\\.b\\+c\\?``.
    """

    return "".join(f"\\{char}" if char in _RE2_METACHARACTERS else char for char in term)


def _term_body(term: str, *, use_whole_word: bool) -> str:
    """Build one term's pattern body.

    ``use_whole_word`` true wraps the escaped term in ASCII word boundaries.
    False leaves the escaped term as a substring.

    Examples
    --------
    ``climate`` with ``use_whole_word`` true becomes ``\\bclimate\\b``.
    ``#climate`` with ``use_whole_word`` false becomes ``#climate``.
    """

    escaped = _escape_regex(term)
    if use_whole_word:
        return rf"\b{escaped}\b"
    return escaped


def _term_pattern(term: str, *, use_whole_word: bool) -> str:
    return f"(?i){_term_body(term, use_whole_word=use_whole_word)}"


def _any_pattern(terms: list[str], *, use_whole_word: bool) -> str:
    """Build one case-insensitive pattern that matches any term.

    One term is that term's body. Several terms are an alternation.

    Examples
    --------
    ``["trump", "biden"]`` with word boundaries becomes
    ``(?i)(?:\\btrump\\b|\\bbiden\\b)``.
    """

    bodies = [_term_body(term, use_whole_word=use_whole_word) for term in terms]
    if len(bodies) == 1:
        return f"(?i){bodies[0]}"
    return "(?i)(?:" + "|".join(bodies) + ")"


def _regexp_like(pattern: str) -> str:
    """Wrap ``pattern`` in ``regexp_like`` on the post text column.

    Examples
    --------
    ``(?i)\\bclimate\\b`` becomes ``regexp_like("text", '(?i)\\bclimate\\b')``.
    """

    return f"regexp_like({_quote(TEXT_COLUMN)}, {_sql_string(pattern)})"


def _keywords_for_query(keywords: list[str]) -> list[str]:
    """Return the terms that will be embedded.

    Raises
    ------
    ValueError
        When a term is empty, longer than 80 characters, or the list has more
        than 8 terms. Validation is supposed to catch those first.
    """

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


def _keyword_condition(terms: list[str], match: KeywordMatch, *, use_whole_word: bool) -> str:
    if match == "all":
        predicates = [
            _regexp_like(_term_pattern(term, use_whole_word=use_whole_word)) for term in terms
        ]
        return " AND ".join(predicates)
    return _regexp_like(_any_pattern(terms, use_whole_word=use_whole_word))


def _matched_keywords_expr(terms: list[str], *, use_whole_word: bool) -> str:
    branches = [
        (
            f"WHEN {_regexp_like(_term_pattern(term, use_whole_word=use_whole_word))} "
            f"THEN {_sql_string(term)}"
        )
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
    use_whole_word: bool,
) -> str:
    """Build the WHERE clause, or an empty string when nothing restricts the scan.

    The end date is exclusive at the next midnight, so the UTC calendar day
    ``end_date`` is included. A keyword predicate is added when ``terms`` is
    non-empty.

    Parameters
    ----------
    use_whole_word : bool
        True wraps each term in an ASCII word boundary. False is a substring.

    Returns
    -------
    str
        A clause starting with ``WHERE``, or ``""``.
    """

    conditions = []
    if start_date is not None:
        conditions.append(f"{PARTITION_SOURCE_COLUMN} >= {_timestamp(start_date)}")
    if end_date is not None:
        conditions.append(f"{PARTITION_SOURCE_COLUMN} < {_timestamp(end_date + timedelta(days=1))}")
    if terms:
        conditions.append(_keyword_condition(terms, match, use_whole_word=use_whole_word))

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

    terms = _keywords_for_query(intent.keywords)
    if terms and intent.record_type is not RecordType.POSTS:
        raise ValueError("keywords require posts")

    matched = _matched_keywords_expr(terms, use_whole_word=intent.use_whole_word) if terms else None
    table = f"{GLUE_DATABASE}.{intent.record_type.value}"
    clauses = [
        _select_clause(intent.columns, matched),
        _from_clause(table),
        _where_clause(
            start_date=intent.start_date,
            end_date=intent.end_date,
            terms=terms,
            match=intent.match,
            use_whole_word=intent.use_whole_word,
        ),
        _order_by_clause(),
    ]
    return GeneratedQuery(
        sql="\n".join(clause for clause in clauses if clause),
        record_type=intent.record_type,
    )
