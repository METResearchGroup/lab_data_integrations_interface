"""Postgres bulk loader for mock Parquet data.

Run from repo root with PYTHONPATH=.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import psycopg
from psycopg import sql

DEFAULT_MOCK_DATA_DIR = Path("experiments/database_experiments_2026_05_23/mock_data")


def create_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS follow CASCADE")
        cur.execute('DROP TABLE IF EXISTS "like" CASCADE')
        cur.execute("DROP TABLE IF EXISTS post CASCADE")
        cur.execute('DROP TABLE IF EXISTS "user" CASCADE')

        cur.execute(
            """
            CREATE TABLE "user" (
                user_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE post (
                post_id TEXT PRIMARY KEY,
                author_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE "like" (
                like_id TEXT PRIMARY KEY,
                author_id TEXT NOT NULL,
                post_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE follow (
                follower_id TEXT NOT NULL,
                followee_id TEXT NOT NULL,
                PRIMARY KEY (follower_id, followee_id)
            )
            """
        )
    conn.commit()


def create_indexes(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_post_created_at ON post (created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_post_author_id ON post (author_id)")
        cur.execute('CREATE INDEX IF NOT EXISTS idx_like_author_id ON "like" (author_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_like_post_id ON "like" (post_id)')
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_post_text_trump
            ON post USING gin (text gin_trgm_ops)
            """
        )
    conn.commit()


def _bulk_insert(conn: psycopg.Connection, table: str, frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    columns = list(frame.columns)
    quoted_table = '"user"' if table == "user" else ('"like"' if table == "like" else table)
    placeholders = sql.SQL(", ").join(sql.Placeholder() * len(columns))
    query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.SQL(quoted_table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        placeholders,
    )
    rows = [tuple(row) for row in frame.itertuples(index=False, name=None)]
    with conn.cursor() as cur:
        cur.executemany(query, rows)
    conn.commit()
    return len(rows)


def load_parquet(conn: psycopg.Connection, mock_data_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in ("user", "post", "like", "follow"):
        frame = pd.read_parquet(mock_data_dir / f"{table}.parquet")
        counts[table] = _bulk_insert(conn, table, frame)
    return counts


def ensure_extensions(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    conn.commit()


def load_mock_data(dsn: str, mock_data_dir: Path) -> dict[str, int]:
    with psycopg.connect(dsn) as conn:
        ensure_extensions(conn)
        create_schema(conn)
        counts = load_parquet(conn, mock_data_dir)
        create_indexes(conn)
        print(f"Loaded Postgres tables: {counts}")
        return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load mock Parquet data into Postgres")
    parser.add_argument("--postgres-dsn", required=True)
    parser.add_argument("--mock-data-dir", type=Path, default=DEFAULT_MOCK_DATA_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_mock_data(args.postgres_dsn, args.mock_data_dir)


if __name__ == "__main__":
    main()
