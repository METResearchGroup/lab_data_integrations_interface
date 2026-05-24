"""SQLite benchmark runner with per-thread connection cache.

Run from repo root:
    PYTHONPATH=. uv run python -c "from experiments.database_experiments_2026_05_23.sqlite.runner import SQLiteRunner"
"""

from __future__ import annotations

import threading
from pathlib import Path

from experiments.database_experiments_2026_05_23.queries import QueryId
from experiments.database_experiments_2026_05_23.sqlite.loader import db_path, load_mock_data
from experiments.database_experiments_2026_05_23.sqlite.queries import SQLiteQueryExecutor


class SQLiteRunner:
    name = "sqlite"

    def __init__(self, sqlite_data_dir: Path) -> None:
        self.sqlite_data_dir = sqlite_data_dir
        self._local = threading.local()
        self._load_counts: dict[str, int] | None = None

    def setup(self, mock_data_dir: Path) -> None:
        self._load_counts = load_mock_data(mock_data_dir, self.sqlite_data_dir)

    def _executor(self) -> SQLiteQueryExecutor:
        executor = getattr(self._local, "executor", None)
        if executor is None:
            executor = SQLiteQueryExecutor(self.sqlite_data_dir)
            self._local.executor = executor
        return executor

    def run_query(self, query_id: QueryId, *, author_id: str | None) -> None:
        self._executor().run_query(query_id, author_id=author_id)

    def collect_storage_metrics(self) -> dict:
        file_sizes: dict[str, int] = {}
        wal_sizes: dict[str, int] = {}
        for table in ("user", "post", "like", "follow"):
            path = db_path(self.sqlite_data_dir, table)
            file_sizes[table] = path.stat().st_size if path.exists() else 0
            wal_path = Path(f"{path}-wal")
            wal_sizes[table] = wal_path.stat().st_size if wal_path.exists() else 0
        return {
            "file_sizes_bytes": file_sizes,
            "wal_sizes_bytes": wal_sizes,
            "total_size_bytes": sum(file_sizes.values()),
            "total_wal_bytes": sum(wal_sizes.values()),
        }

    def teardown(self) -> None:
        return None
