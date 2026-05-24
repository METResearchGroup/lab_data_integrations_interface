"""SQLite bulk loader — one file per table with WAL pragmas.

Run from repo root:
    PYTHONPATH=. uv run python experiments/database_experiments_2026_05_23/sqlite/loader.py \
      --mock-data-dir experiments/database_experiments_2026_05_23/mock_data \
      --output-dir experiments/database_experiments_2026_05_23/sqlite_data
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

DEFAULT_MOCK_DATA_DIR = Path("experiments/database_experiments_2026_05_23/mock_data")
DEFAULT_OUTPUT_DIR = Path("experiments/database_experiments_2026_05_23/sqlite_data")

TABLE_SCHEMAS: dict[str, str] = {
    "user": """
        CREATE TABLE IF NOT EXISTS user (
            user_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
    """,
    "post": """
        CREATE TABLE IF NOT EXISTS post (
            post_id TEXT PRIMARY KEY,
            author_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            text TEXT NOT NULL
        )
    """,
    "like": """
        CREATE TABLE IF NOT EXISTS like (
            like_id TEXT PRIMARY KEY,
            author_id TEXT NOT NULL,
            post_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """,
    "follow": """
        CREATE TABLE IF NOT EXISTS follow (
            follower_id TEXT NOT NULL,
            followee_id TEXT NOT NULL,
            PRIMARY KEY (follower_id, followee_id)
        )
    """,
}

INSERT_COLUMNS: dict[str, tuple[str, ...]] = {
    "user": ("user_id", "created_at"),
    "post": ("post_id", "author_id", "created_at", "text"),
    "like": ("like_id", "author_id", "post_id", "created_at"),
    "follow": ("follower_id", "followee_id"),
}


def apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("PRAGMA mmap_size=268435456")
    conn.execute("PRAGMA temp_store=MEMORY")


def db_path(output_dir: Path, table: str) -> Path:
    return output_dir / f"{table}.sqlite"


def load_table(conn: sqlite3.Connection, table: str, frame: pd.DataFrame) -> int:
    conn.execute(f"DELETE FROM {table}")
    columns = INSERT_COLUMNS[table]
    placeholders = ", ".join("?" for _ in columns)
    query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    rows = [tuple(row[col] for col in columns) for _, row in frame.iterrows()]
    conn.executemany(query, rows)
    return len(rows)


def load_mock_data(mock_data_dir: Path, output_dir: Path) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    for table in TABLE_SCHEMAS:
        path = db_path(output_dir, table)
        if path.exists():
            path.unlink()
        conn = sqlite3.connect(path)
        try:
            apply_pragmas(conn)
            conn.execute(TABLE_SCHEMAS[table])
            frame = pd.read_parquet(mock_data_dir / f"{table}.parquet")
            conn.execute("BEGIN")
            counts[table] = load_table(conn, table, frame)
            conn.commit()
        finally:
            conn.close()

    print(f"Loaded SQLite files in {output_dir}: {counts}")
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load mock Parquet data into SQLite files")
    parser.add_argument("--mock-data-dir", type=Path, default=DEFAULT_MOCK_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_mock_data(args.mock_data_dir, args.output_dir)


if __name__ == "__main__":
    main()
