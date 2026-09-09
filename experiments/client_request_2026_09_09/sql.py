"""Build per-candidate Athena UNLOAD SQL for the name-match export.

Run from the repo root:

    PYTHONPATH=. uv run python experiments/client_request_2026_09_09/main.py
"""

from __future__ import annotations

from datetime import date, timedelta

from experiments.client_request_2026_09_09.constants import (
    EXCLUSIVE_END_OFFSET_DAYS,
    GLUE_TABLE,
    MIDNIGHT_CLOCK,
    UNLOAD_SQL_COMPRESSION,
    UNLOAD_SQL_FORMAT,
    Candidate,
    query_end_date,
    query_start_date,
)
from experiments.client_request_2026_09_09.schemas import (
    COLUMN_CREATED_AT,
    COLUMN_DID,
    COLUMN_MATCHED_CANDIDATE,
    COLUMN_MATCHED_NAME_STRING,
    COLUMN_TEXT,
    COLUMN_URI,
)

LIKE_WILDCARD = "%"
SQL_STRING_QUOTE = "'"
ESCAPED_SQL_STRING_QUOTE = "''"


def escape_sql_literal(value: str) -> str:
    """Escape a SQL string literal by doubling single quotes.

    Parameters
    ----------
    value
        Raw string interpolated into a quoted SQL literal.

    Returns
    -------
    str
        ``value`` with each ``'`` replaced by ``''``.
    """

    return value.replace(SQL_STRING_QUOTE, ESCAPED_SQL_STRING_QUOTE)


def _quoted_sql_string(value: str) -> str:
    return f"{SQL_STRING_QUOTE}{escape_sql_literal(value)}{SQL_STRING_QUOTE}"


def _timestamp_literal(day: date) -> str:
    return f"TIMESTAMP '{day.isoformat()} {MIDNIGHT_CLOCK}'"


def _like_predicate(name_string: str) -> str:
    escaped = _quoted_sql_string(name_string)
    wildcard = _quoted_sql_string(LIKE_WILDCARD)
    return f"LOWER({COLUMN_TEXT}) LIKE {wildcard} || {escaped} || {wildcard}"


def _name_match_disjunction(name_strings: tuple[str, ...]) -> str:
    joined = "\n        OR ".join(_like_predicate(name_string) for name_string in name_strings)
    return f"(\n        {joined}\n    )"


def _matched_name_case(name_strings: tuple[str, ...]) -> str:
    branches = []
    for name_string in name_strings:
        when_clause = _like_predicate(name_string)
        then_literal = _quoted_sql_string(name_string)
        branches.append(f"WHEN {when_clause} THEN {then_literal}")
    when_block = "\n            ".join(branches)
    return f"CASE\n            {when_block}\n        END AS {COLUMN_MATCHED_NAME_STRING}"


def _limit_clause(smoke_limit: int | None) -> str:
    if not isinstance(smoke_limit, int):
        return ""
    return f"\n    LIMIT {smoke_limit}"


def _inner_select(candidate: Candidate, run_date: date, smoke_limit: int | None) -> str:
    start_day = query_start_date(candidate.primary_date)
    end_exclusive = query_end_date(run_date) + timedelta(days=EXCLUSIVE_END_OFFSET_DAYS)
    matched_id_literal = _quoted_sql_string(candidate.candidate_id)
    return f"""SELECT
        {COLUMN_URI},
        {COLUMN_DID},
        {COLUMN_TEXT},
        CAST({COLUMN_CREATED_AT} AS TIMESTAMP) AS {COLUMN_CREATED_AT},
        {matched_id_literal} AS {COLUMN_MATCHED_CANDIDATE},
        {_matched_name_case(candidate.name_strings)}
    FROM {GLUE_TABLE}
    WHERE {COLUMN_CREATED_AT} >= {_timestamp_literal(start_day)}
        AND {COLUMN_CREATED_AT} < {_timestamp_literal(end_exclusive)}
        AND {_name_match_disjunction(candidate.name_strings)}{_limit_clause(smoke_limit)}"""


def build_unload_sql(
    candidate: Candidate,
    *,
    run_date: date,
    s3_uri: str,
    smoke_limit: int | None = None,
) -> str:
    """Return Athena UNLOAD SQL for one candidate's name-match window.

    Parameters
    ----------
    candidate
        Person whose ``name_strings`` are matched against post text.
    run_date
        Inclusive UTC end date of the scan.
    s3_uri
        UNLOAD destination prefix, including the trailing slash.
    smoke_limit
        If an ``int``, appended as ``LIMIT`` on the inner select. ``None``
        means no row cap.

    Returns
    -------
    str
        Full ``UNLOAD`` statement. Does not include the Glue database name in
        ``FROM``.
    """

    inner_select = _inner_select(candidate, run_date, smoke_limit)
    return f"""UNLOAD (
    {inner_select}
)
TO '{s3_uri}'
WITH (format = '{UNLOAD_SQL_FORMAT}', compression = '{UNLOAD_SQL_COMPRESSION}')"""
