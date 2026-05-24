"""DuckDB benchmark runner with Parquet views and EXPLAIN ANALYZE profiling.

Run from repo root:
    PYTHONPATH=. uv run python -c "from experiments.database_experiments_2026_05_23.duckdb.runner import DuckDBRunner"
"""

from __future__ import annotations

import importlib
import re
import threading
from pathlib import Path

import pyarrow.parquet as pq

from experiments.database_experiments_2026_05_23.config import ensure_repo_import_path
from experiments.database_experiments_2026_05_23.duckdb.queries import build_params, get_query
from experiments.database_experiments_2026_05_23.queries import QUERY_SPECS, QueryId

_duckdb_lock = threading.Lock()
_duckdb_module = None


def _get_duckdb():
    global _duckdb_module
    if _duckdb_module is not None:
        return _duckdb_module
    with _duckdb_lock:
        if _duckdb_module is not None:
            return _duckdb_module
        ensure_repo_import_path()
        _duckdb_module = importlib.import_module("duckdb")
        if not hasattr(_duckdb_module, "connect"):
            raise ImportError("Installed duckdb package is missing connect()")
        return _duckdb_module


def _range_params() -> dict[str, str]:
    return {
        "today_start": format_range_start(start_of_today()),
        "week_start": format_range_start(days_ago(7)),
        "three_weeks_start": format_range_start(days_ago(21)),
    }


def _register_parquet_views(conn: object, mock_data_dir: Path) -> None:
    for table in ("user", "post", "like", "follow"):
        parquet_path = (mock_data_dir / f"{table}.parquet").as_posix()
        view_name = f'"{table}"' if table in ("user", "like") else table
        conn.execute(
            f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_parquet('{parquet_path}')"
        )


class DuckDBRunner:
    name = "duckdb"

    def __init__(self, mock_data_dir: Path) -> None:
        self.mock_data_dir = mock_data_dir
        self._local = threading.local()
        self.profiles: dict[str, dict] = {}

    def _connect(self) -> object:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = _get_duckdb().connect(database=":memory:")
            _register_parquet_views(conn, self.mock_data_dir)
            self._local.conn = conn
        return conn

    def setup(self, mock_data_dir: Path) -> None:
        self.mock_data_dir = mock_data_dir

    def run_query(self, query_id: QueryId, *, author_id: str | None) -> None:
        conn = self._connect()
        sql_text = get_query(query_id)
        params = build_params(query_id, author_id=author_id)
        conn.execute(sql_text, params).fetchall()

    def _parse_explain(self, plan_text: str) -> dict:
        bytes_read = 0
        for match in re.finditer(r"(\d+)\ bytes", plan_text):
            bytes_read = max(bytes_read, int(match.group(1)))
        spill_match = re.search(r" spilled (\d+) bytes", plan_text)
        temp_spill_bytes = int(spill_match.group(1)) if spill_match else 0
        scan_summary = "parquet_scan" if "READ_PARQUET" in plan_text.upper() else "unknown"
        return {
            "parquet_bytes_read": bytes_read,
            "temp_spill_bytes": temp_spill_bytes,
            "scan_summary": scan_summary,
            "plan_excerpt": plan_text[:500],
        }

    def run_profiles(self, author_ids: list[str]) -> dict[str, dict]:
        conn = _get_duckdb().connect(database=":memory:")
        _register_parquet_views(conn, self.mock_data_dir)

        profiles: dict[str, dict] = {}
        sample_author = author_ids[0] if author_ids else None
        for spec in QUERY_SPECS:
            sql_text = get_query(spec.query_id)
            params = build_params(
                spec.query_id,
                author_id=sample_author if spec.requires_author_id else None,
            )
            plan = conn.execute(f"EXPLAIN ANALYZE {sql_text}", params).fetchall()
            plan_text = "\n".join(row[1] for row in plan if len(row) > 1)
            profiles[spec.query_id.value] = self._parse_explain(plan_text)
        conn.close()
        self.profiles = profiles
        return profiles

    def collect_storage_metrics(self) -> dict:
        parquet_files = sorted(self.mock_data_dir.glob("*.parquet"))
        file_sizes = {path.name: path.stat().st_size for path in parquet_files}
        total_size = sum(file_sizes.values())

        row_group_sizes: dict[str, list[int]] = {}
        for path in parquet_files:
            metadata = pq.read_metadata(path)
            row_group_sizes[path.name] = [
                metadata.row_group(group_idx).total_byte_size
                for group_idx in range(metadata.num_row_groups)
            ]

        metadata_files = list(self.mock_data_dir.glob("*.duckdb"))
        return {
            "parquet_file_count": len(parquet_files),
            "parquet_file_sizes_bytes": file_sizes,
            "parquet_total_size_bytes": total_size,
            "parquet_row_group_sizes_bytes": row_group_sizes,
            "parquet_partition_dir_count": 1,
            "duckdb_metadata_files": [path.name for path in metadata_files],
            "compression_ratio_estimate": None,
        }

    def teardown(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
