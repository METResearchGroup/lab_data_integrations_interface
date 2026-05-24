"""Orchestrate database benchmark experiments across Postgres, SQLite, and DuckDB.

Run from repo root with PYTHONPATH=.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import random
import sys
from pathlib import Path

import pandas as pd
import psycopg
import pyarrow.parquet as pq

from experiments.database_experiments_2026_05_23.config import (
    BACKEND_ORDER,
    DEFAULT_MOCK_DATA_DIR,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SQLITE_DATA_DIR,
    SAMPLE_AUTHOR_COUNT,
    BenchmarkConfig,
    ensure_repo_import_path,
)
from experiments.database_experiments_2026_05_23.date_utils import (
    days_ago,
    format_range_start,
    start_of_today,
)
from experiments.database_experiments_2026_05_23.harness import run_benchmark
from experiments.database_experiments_2026_05_23.postgres.runner import PostgresRunner, default_dsn
from experiments.database_experiments_2026_05_23.queries import QUERY_SPECS
from experiments.database_experiments_2026_05_23.sqlite.runner import SQLiteRunner
from lib.timestamp_utils import get_current_timestamp


def parse_args() -> BenchmarkConfig:
    parser = argparse.ArgumentParser(description="Run database benchmark experiment")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--scale", choices=("smoke", "full"), default="full")
    parser.add_argument("--mock-data-dir", type=Path, default=DEFAULT_MOCK_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--sqlite-data-dir", type=Path, default=DEFAULT_SQLITE_DATA_DIR)
    parser.add_argument("--backends", default=",".join(BACKEND_ORDER))
    parser.add_argument("--postgres-dsn", default=None)
    parser.add_argument("--skip-postgres", action="store_true")
    args = parser.parse_args()

    backends = tuple(part.strip() for part in args.backends.split(",") if part.strip())
    postgres_dsn = args.postgres_dsn or default_dsn()
    if args.skip_postgres:
        backends = tuple(name for name in backends if name != "postgres")

    return BenchmarkConfig(
        threads=args.threads,
        iterations=args.iterations,
        warmup=args.warmup,
        scale=args.scale,
        mock_data_dir=args.mock_data_dir,
        output_dir=args.output_dir,
        sqlite_data_dir=args.sqlite_data_dir,
        backends=backends,
        postgres_dsn=postgres_dsn,
        skip_postgres=args.skip_postgres,
    )


def sample_author_ids(mock_data_dir: Path, count: int, seed: int) -> list[str]:
    posts = pd.read_parquet(mock_data_dir / "post.parquet", columns=["author_id"])
    unique_authors = posts["author_id"].drop_duplicates().tolist()
    rng = random.Random(seed)
    sample_size = min(count, len(unique_authors))
    return rng.sample(unique_authors, k=sample_size)


def load_row_counts(mock_data_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in ("user", "post", "like", "follow"):
        counts[table] = pq.read_metadata(mock_data_dir / f"{table}.parquet").num_rows
    return counts


def engine_versions() -> dict[str, str]:
    versions = {
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    try:
        duckdb_mod = importlib.import_module("duckdb")
        if hasattr(duckdb_mod, "__version__"):
            versions["duckdb"] = duckdb_mod.__version__
        else:
            sys.modules.pop("duckdb", None)
            versions["duckdb"] = importlib.import_module("duckdb").__version__
    except Exception:
        versions["duckdb"] = "unknown"
    try:
        versions["psycopg"] = psycopg.__version__
    except Exception:
        versions["psycopg"] = "unknown"
    return versions


def host_specs() -> dict:
    return {
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "platform": platform.platform(),
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_backend_runner(name: str, config: BenchmarkConfig):
    if name == "postgres":
        if not config.postgres_dsn:
            raise RuntimeError("POSTGRES_DSN or --postgres-dsn is required for postgres backend")
        return PostgresRunner(config.postgres_dsn, config.mock_data_dir)
    if name == "sqlite":
        return SQLiteRunner(config.sqlite_data_dir)
    if name == "duckdb":
        ensure_repo_import_path()
        from experiments.database_experiments_2026_05_23.duckdb.runner import DuckDBRunner

        return DuckDBRunner(config.mock_data_dir)
    raise ValueError(f"Unknown backend: {name}")


def aggregate_metrics(backend_results: dict[str, dict]) -> dict:
    comparison: dict[str, dict] = {}
    for backend_name, payload in backend_results.items():
        comparison[backend_name] = {
            "resources": payload.get("resources", {}),
            "storage": payload.get("storage", {}),
            "queries": {
                query_id: {
                    "p50_ms": stats["p50_ms"],
                    "p90_ms": stats["p90_ms"],
                    "p99_ms": stats["p99_ms"],
                    "qps": stats["qps"],
                }
                for query_id, stats in payload.get("queries", {}).items()
            },
        }
        if backend_name == "duckdb":
            comparison[backend_name]["profiles"] = payload.get("profiles", {})
    return {"backends": comparison}


def main() -> None:
    ensure_repo_import_path()
    config = parse_args()
    run_timestamp = get_current_timestamp()
    run_dir = config.output_dir / run_timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    author_ids = sample_author_ids(config.mock_data_dir, SAMPLE_AUTHOR_COUNT, seed=42)
    row_counts = load_row_counts(config.mock_data_dir)

    timestamp_ranges = {
        "today_start": format_range_start(start_of_today()),
        "week_start": format_range_start(days_ago(7)),
        "three_weeks_start": format_range_start(days_ago(21)),
    }

    backend_results: dict[str, dict] = {}
    run_log: list[str] = []

    for backend_name in config.backends:
        print(f"Running backend: {backend_name}")
        run_log.append(backend_name)
        runner = build_backend_runner(backend_name, config)
        runner.setup(config.mock_data_dir)

        storage_after_load = runner.collect_storage_metrics()

        query_results, resources = run_benchmark(
            runner,
            threads=config.threads,
            iterations=config.iterations,
            warmup=config.warmup,
            author_ids=author_ids,
        )

        storage_after_benchmark = runner.collect_storage_metrics()
        profiles = {}
        if backend_name == "duckdb":
            profiles = runner.run_profiles(author_ids)

        backend_payload = {
            "backend": backend_name,
            "threads": config.threads,
            "iterations": config.iterations,
            "warmup": config.warmup,
            "queries": query_results,
            "resources": resources,
            "storage_after_load": storage_after_load,
            "storage_after_benchmark": storage_after_benchmark,
        }
        if profiles:
            backend_payload["profiles"] = profiles

        write_json(run_dir / f"{backend_name}_results.json", backend_payload)
        backend_results[backend_name] = backend_payload
        runner.teardown()

    metadata = {
        "run_timestamp": run_timestamp,
        "scale": config.scale,
        "threads": config.threads,
        "iterations": config.iterations,
        "warmup": config.warmup,
        "backend_order": list(config.backends),
        "run_log": run_log,
        "timestamp_ranges": timestamp_ranges,
        "sample_author_ids": author_ids,
        "engine_versions": engine_versions(),
        "host_specs": host_specs(),
        "mock_data_row_counts": row_counts,
        "query_specs": [
            {
                "query_id": spec.query_id.value,
                "category": spec.category.value,
                "description": spec.description,
                "requires_author_id": spec.requires_author_id,
            }
            for spec in QUERY_SPECS
        ],
    }
    write_json(run_dir / "metadata.json", metadata)
    write_json(run_dir / "metrics.json", aggregate_metrics(backend_results))

    print(f"Benchmark complete. Results written to {run_dir}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
