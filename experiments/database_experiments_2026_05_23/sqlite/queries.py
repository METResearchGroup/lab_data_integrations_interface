"""SQLite query implementations with in-Python cross-table joins.

Run from repo root with PYTHONPATH=.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from experiments.database_experiments_2026_05_23.date_utils import (
    date_only_key,
    days_ago,
    format_range_start,
    start_of_today,
)
from experiments.database_experiments_2026_05_23.queries import QueryId
from experiments.database_experiments_2026_05_23.sqlite.loader import apply_pragmas, db_path


@dataclass
class SQLiteQueryExecutor:
    sqlite_data_dir: Path

    def _connect(self, table: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path(self.sqlite_data_dir, table))
        apply_pragmas(conn)
        return conn

    def run_query(self, query_id: QueryId, *, author_id: str | None) -> None:
        if query_id == QueryId.POSTS_TODAY_LIMIT_100:
            self._posts_today_limit_100()
        elif query_id == QueryId.TOP_100_POSTERS_PAST_WEEK:
            self._top_100_posters_past_week()
        elif query_id == QueryId.TRUMP_POST_COUNT_PAST_WEEK:
            self._trump_post_count_past_week()
        elif query_id == QueryId.POSTS_PER_DAY_PAST_3_WEEKS:
            self._posts_per_day_past_3_weeks()
        elif query_id == QueryId.LAST_10_POSTS_BY_AUTHOR:
            self._last_10_posts_by_author(author_id)
        elif query_id == QueryId.LAST_10_LIKED_POSTS_BY_AUTHOR:
            self._last_10_liked_posts_by_author(author_id)
        else:
            raise ValueError(f"Unknown query: {query_id}")

    def _posts_today_limit_100(self) -> None:
        today_start = format_range_start(start_of_today())
        with self._connect("post") as conn:
            rows = conn.execute(
                """
                SELECT post_id, author_id, created_at, text
                FROM post
                WHERE created_at >= ?
                ORDER BY created_at DESC
                LIMIT 100
                """,
                (today_start,),
            ).fetchall()
        _ = rows

    def _top_100_posters_past_week(self) -> None:
        week_start = format_range_start(days_ago(7))
        with self._connect("post") as conn:
            rows = conn.execute(
                """
                SELECT author_id, COUNT(*) AS post_count
                FROM post
                WHERE created_at >= ?
                GROUP BY author_id
                ORDER BY post_count DESC
                LIMIT 100
                """,
                (week_start,),
            ).fetchall()
        _ = rows

    def _trump_post_count_past_week(self) -> None:
        week_start = format_range_start(days_ago(7))
        with self._connect("post") as conn:
            count = conn.execute(
                """
                SELECT COUNT(*)
                FROM post
                WHERE created_at >= ?
                  AND LOWER(text) LIKE '%trump%'
                """,
                (week_start,),
            ).fetchone()[0]
        _ = count

    def _posts_per_day_past_3_weeks(self) -> None:
        three_weeks_start = format_range_start(days_ago(21))
        with self._connect("post") as conn:
            rows = conn.execute(
                """
                SELECT created_at
                FROM post
                WHERE created_at >= ?
                """,
                (three_weeks_start,),
            ).fetchall()
        counts = Counter(date_only_key(row[0]) for row in rows)
        _ = counts

    def _last_10_posts_by_author(self, author_id: str | None) -> None:
        if author_id is None:
            return
        with self._connect("post") as conn:
            rows = conn.execute(
                """
                SELECT post_id, author_id, created_at, text
                FROM post
                WHERE author_id = ?
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (author_id,),
            ).fetchall()
        _ = rows

    def _last_10_liked_posts_by_author(self, author_id: str | None) -> None:
        if author_id is None:
            return
        with self._connect("like") as like_conn:
            likes = like_conn.execute(
                """
                SELECT post_id, created_at
                FROM like
                WHERE author_id = ?
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (author_id,),
            ).fetchall()
        if not likes:
            return
        post_ids = [row[0] for row in likes]
        placeholders = ", ".join("?" for _ in post_ids)
        with self._connect("post") as post_conn:
            rows = post_conn.execute(
                f"""
                SELECT post_id, author_id, created_at, text
                FROM post
                WHERE post_id IN ({placeholders})
                """,
                post_ids,
            ).fetchall()
        _ = rows
