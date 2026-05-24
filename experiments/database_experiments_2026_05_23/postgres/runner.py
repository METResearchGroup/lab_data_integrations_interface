"""Postgres benchmark runner with connection pool and storage metrics.

Run from repo root with PYTHONPATH=.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

from experiments.database_experiments_2026_05_23.postgres.loader import load_mock_data
from experiments.database_experiments_2026_05_23.postgres.queries import build_params, get_query
from experiments.database_experiments_2026_05_23.queries import QueryId


class PostgresRunner:
    name = "postgres"

    def __init__(self, dsn: str, mock_data_dir: Path) -> None:
        self.dsn = dsn
        self.mock_data_dir = mock_data_dir
        self.pool: ConnectionPool | None = None
        self._wal_start_bytes: int | None = None

    def setup(self, mock_data_dir: Path) -> None:
        self.mock_data_dir = mock_data_dir
        load_mock_data(self.dsn, mock_data_dir)
        self.pool = ConnectionPool(self.dsn, min_size=1, max_size=16, open=True)
        with self.pool.connection() as conn:
            self._wal_start_bytes = self._current_wal_bytes(conn)

    def run_query(self, query_id: QueryId, *, author_id: str | None) -> None:
        if self.pool is None:
            raise RuntimeError("PostgresRunner.setup() must be called first")
        sql_text = get_query(query_id)
        params = build_params(query_id, author_id=author_id)
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(sql_text, params)
            _ = cur.fetchall()

    def _current_wal_bytes(self, conn: psycopg.Connection) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(size), 0)
                FROM pg_ls_waldir()
                """
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def collect_storage_metrics(self) -> dict:
        if self.pool is None:
            return {}
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_database_size(current_database())")
            db_size = int(cur.fetchone()[0])

            table_sizes: dict[str, int] = {}
            index_sizes: dict[str, int] = {}
            for table in ("user", "post", "like", "follow"):
                quoted = f'"{table}"' if table in ("user", "like") else table
                cur.execute(f"SELECT pg_relation_size('{quoted}'::regclass)")
                table_sizes[table] = int(cur.fetchone()[0])
                cur.execute(f"SELECT pg_indexes_size('{quoted}'::regclass)")
                index_sizes[table] = int(cur.fetchone()[0])

            wal_end_bytes = self._current_wal_bytes(conn)
            wal_growth_bytes = (
                wal_end_bytes - self._wal_start_bytes if self._wal_start_bytes is not None else 0
            )

        return {
            "database_size_bytes": db_size,
            "table_sizes_bytes": table_sizes,
            "index_sizes_bytes": index_sizes,
            "wal_bytes": wal_end_bytes,
            "wal_growth_bytes": wal_growth_bytes,
        }

    def teardown(self) -> None:
        if self.pool is not None:
            self.pool.close()
            self.pool = None


def default_dsn() -> str | None:
    return os.environ.get("POSTGRES_DSN")
