"""Postgres SQL implementations of the six benchmark queries.

Run from repo root with PYTHONPATH=.
"""

from __future__ import annotations

from experiments.database_experiments_2026_05_23.date_utils import (
    days_ago,
    format_range_start,
    start_of_today,
)
from experiments.database_experiments_2026_05_23.queries import QueryId

POSTGRES_QUERIES: dict[QueryId, tuple[str, dict[str, str]]] = {
    QueryId.POSTS_TODAY_LIMIT_100: (
        """
        SELECT post_id, author_id, created_at, text
        FROM post
        WHERE created_at >= %(today_start)s
        ORDER BY created_at DESC
        LIMIT 100
        """,
        {},
    ),
    QueryId.TOP_100_POSTERS_PAST_WEEK: (
        """
        SELECT author_id, COUNT(*) AS post_count
        FROM post
        WHERE created_at >= %(week_start)s
        GROUP BY author_id
        ORDER BY post_count DESC
        LIMIT 100
        """,
        {},
    ),
    QueryId.TRUMP_POST_COUNT_PAST_WEEK: (
        """
        SELECT COUNT(*) AS trump_count
        FROM post
        WHERE created_at >= %(week_start)s
          AND text ILIKE '%%Trump%%'
        """,
        {},
    ),
    QueryId.POSTS_PER_DAY_PAST_3_WEEKS: (
        """
        SELECT LEFT(created_at, 10) AS day, COUNT(*) AS post_count
        FROM post
        WHERE created_at >= %(three_weeks_start)s
        GROUP BY day
        ORDER BY day
        """,
        {},
    ),
    QueryId.LAST_10_POSTS_BY_AUTHOR: (
        """
        SELECT post_id, author_id, created_at, text
        FROM post
        WHERE author_id = %(author_id)s
        ORDER BY created_at DESC
        LIMIT 10
        """,
        {},
    ),
    QueryId.LAST_10_LIKED_POSTS_BY_AUTHOR: (
        """
        SELECT p.post_id, p.author_id, p.created_at, p.text
        FROM "like" l
        JOIN post p ON p.post_id = l.post_id
        WHERE l.author_id = %(author_id)s
        ORDER BY l.created_at DESC
        LIMIT 10
        """,
        {},
    ),
}


def build_params(query_id: QueryId, *, author_id: str | None) -> dict[str, str]:
    params: dict[str, str] = {}
    if query_id == QueryId.POSTS_TODAY_LIMIT_100:
        params["today_start"] = format_range_start(start_of_today())
    elif query_id in (
        QueryId.TOP_100_POSTERS_PAST_WEEK,
        QueryId.TRUMP_POST_COUNT_PAST_WEEK,
    ):
        params["week_start"] = format_range_start(days_ago(7))
    elif query_id == QueryId.POSTS_PER_DAY_PAST_3_WEEKS:
        params["three_weeks_start"] = format_range_start(days_ago(21))
    if author_id is not None:
        params["author_id"] = author_id
    return params


def get_query(query_id: QueryId) -> str:
    sql_text, _extra = POSTGRES_QUERIES[query_id]
    return sql_text
