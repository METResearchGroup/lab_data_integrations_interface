"""Dedup benchmark: S3+SQLite vs DynamoDB.

Runs all (batch_size × table_size) combinations for both backends, writes
results to data/{timestamp}/.

Run from repo root:
    PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/main.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table

from experiments.dedup_comparison_2026_06_12.athena_backend import AthenaBackend
from experiments.dedup_comparison_2026_06_12.duckdb_backend import DuckDBBackend
from experiments.dedup_comparison_2026_06_12.dynamodb_backend import DynamoDBBackend
from experiments.dedup_comparison_2026_06_12.harness import run_benchmark
from experiments.dedup_comparison_2026_06_12.metrics import (
    compute_scale_degradation,
    estimate_dynamodb_cost_per_1000_runs,
    estimate_sqlite_cost_per_1000_runs,
)
from experiments.dedup_comparison_2026_06_12.sqlite_backend import SQLiteBackend
from lib.timestamp_utils import get_current_timestamp

console = Console()

MOCK_DATA_DIR = Path(__file__).parent / "mock_data"
DATA_DIR = Path(__file__).parent / "data"

BATCH_SIZES = [100, 1_000, 5_000, 10_000]
TABLE_SIZES = [0, 10_000, 100_000]

N_RUNS = 1
WARMUP = 0


def load_uris(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_all_mock_data() -> tuple[dict[int, list[str]], dict[int, list[str]]]:
    batch_uris: dict[int, list[str]] = {}
    for n in BATCH_SIZES:
        path = MOCK_DATA_DIR / f"uris_{n}.txt"
        if not path.exists():
            print(f"ERROR: {path} not found. Run generate_mock_data.py first.", file=sys.stderr)
            sys.exit(1)
        batch_uris[n] = load_uris(path)

    seed_uris: dict[int, list[str]] = {0: []}
    for size, label in [(10_000, "10k"), (100_000, "100k")]:
        path = MOCK_DATA_DIR / f"uris_seed_{label}.txt"
        if not path.exists():
            print(f"ERROR: {path} not found. Run generate_mock_data.py first.", file=sys.stderr)
            sys.exit(1)
        seed_uris[size] = load_uris(path)

    return batch_uris, seed_uris


def run_backend(
    backend_name: str,
    backend: SQLiteBackend | DynamoDBBackend | AthenaBackend | DuckDBBackend,
    batch_uris: dict[int, list[str]],
    seed_uris: dict[int, list[str]],
    *,
    table_sizes: list[int],
    out_dir: Path,
) -> dict[str, object]:
    results: dict[str, object] = {}
    partial_path = out_dir / f"{backend_name}_results.json"

    for table_size in table_sizes:
        if table_size not in seed_uris:
            continue
        # Seed once per table_size — cleanup() between runs keeps the table at
        # seed state, so we don't need to re-seed for each batch_size.
        print(f"  [{backend_name}] clearing table...", end=" ", flush=True)
        backend.clear_all()
        print(f"seeding {len(seed_uris[table_size]):>9,} URIs...", end=" ", flush=True)
        if seed_uris[table_size]:
            backend.seed(seed_uris[table_size])
        print("done")

        for batch_size in BATCH_SIZES:
            key = f"batch_{batch_size}_table_{table_size}"
            label = f"{backend_name} | batch={batch_size:>6,} table={table_size:>9,}"
            print(f"  {label}")
            result = run_benchmark(
                backend,
                batch_uris[batch_size],
                n_runs=N_RUNS,
                warmup=WARMUP,
                label=label,
            )
            results[key] = result

        write_json(partial_path, results)
        print(f"  [{backend_name}] checkpoint saved (table_size={table_size:,})")

    return results


def print_results_table(
    sqlite_results: dict,
    dynamodb_results: dict,
    athena_results: dict,
    duckdb_results: dict,
    *,
    table_sizes: list[int],
) -> None:
    table = Table(
        title="Dedup Benchmark Results",
        box=box.SIMPLE_HEAVY,
        show_lines=True,
    )

    table.add_column("Backend", style="bold cyan", no_wrap=True)
    table.add_column("Batch", justify="right", style="white")
    table.add_column("Table Size", justify="right", style="white")
    table.add_column("Check ms", justify="right", style="green")
    table.add_column("Write ms", justify="right", style="yellow")
    table.add_column("E2E ms", justify="right", style="blue")
    table.add_column("HTTP Calls", justify="right", style="white")
    table.add_column("RSS MB", justify="right", style="magenta")

    backends = []
    if sqlite_results:
        backends.append(("S3+SQLite", sqlite_results))
    if dynamodb_results:
        backends.append(("DynamoDB", dynamodb_results))
    if athena_results:
        backends.append(("S3+Athena", athena_results))
    if duckdb_results:
        backends.append(("S3+DuckDB", duckdb_results))

    for backend_name, results in backends:
        first_row = True
        for table_size in table_sizes:
            for batch_size in BATCH_SIZES:
                key = f"batch_{batch_size}_table_{table_size}"
                if key not in results:
                    continue
                r = results[key]
                table.add_row(
                    backend_name if first_row else "",
                    f"{batch_size:,}",
                    f"{table_size:,}",
                    f"{r['check_latency']['ms']:.1f}ms",
                    f"{r['write_latency']['ms']:.1f}ms",
                    f"{r['end_to_end_latency']['ms']:.1f}ms",
                    str(r["http_call_count"]),
                    f"{r['peak_rss_mb']:.1f}",
                )
                first_row = False

    console.print()
    console.print(table)


def build_metrics(
    sqlite_results: dict,
    dynamodb_results: dict,
    *,
    table_sizes: list[int],
) -> dict:
    side_by_side = {}
    for table_size in table_sizes:
        for batch_size in BATCH_SIZES:
            key = f"batch_{batch_size}_table_{table_size}"
            if key in sqlite_results and key in dynamodb_results:
                side_by_side[key] = {
                    "sqlite": sqlite_results[key],
                    "dynamodb": dynamodb_results[key],
                }

    scale_degradation = {}
    if 100_000 in table_sizes:
        for batch_size in BATCH_SIZES:
            scale_degradation[f"batch_{batch_size}"] = {
                "sqlite": compute_scale_degradation(sqlite_results, batch_size=batch_size),
                "dynamodb": compute_scale_degradation(dynamodb_results, batch_size=batch_size),
            }

    cost = {}
    for table_size in table_sizes:
        for batch_size in BATCH_SIZES:
            cost[f"batch_{batch_size}_table_{table_size}"] = {
                "sqlite": estimate_sqlite_cost_per_1000_runs(table_size_uris=table_size),
                "dynamodb": estimate_dynamodb_cost_per_1000_runs(
                    table_size_uris=table_size,
                    batch_size_uris=batch_size,
                    avg_new_uris_per_run=batch_size,
                ),
            }

    recommendation = _build_recommendation(scale_degradation, sqlite_results, dynamodb_results)

    return {
        "side_by_side": side_by_side,
        "scale_degradation_coefficient": scale_degradation,
        "estimated_cost_per_1000_runs": cost,
        "recommendation": recommendation,
    }


def _build_recommendation(
    scale_degradation: dict,
    sqlite_results: dict,
    dynamodb_results: dict,
) -> str:
    reasons: list[str] = []

    for batch_size in BATCH_SIZES:
        key = f"batch_{batch_size}"
        if key in scale_degradation:
            sqlite_coeff = scale_degradation[key].get("sqlite", float("nan"))
            if not isinstance(sqlite_coeff, float):
                continue
            if sqlite_coeff > 3.0:
                reasons.append(
                    f"S3+SQLite scale degradation at 100K table = {sqlite_coeff:.1f}x "
                    f"(batch={batch_size}) exceeds 3x threshold"
                )

    key_100k_10k = "batch_10000_table_100000"
    if key_100k_10k in sqlite_results:
        check_ms = sqlite_results[key_100k_10k]["check_latency"]["ms"]
        if check_ms > 5000:
            reasons.append(f"S3+SQLite check at 100K table = {check_ms:.0f}ms exceeds 5s threshold")

    if reasons:
        return "USE DYNAMODB. Reasons: " + "; ".join(reasons)
    return (
        "USE S3+SQLITE. Scale degradation is within acceptable bounds. "
        "Simpler infrastructure, no new AWS service required."
    )


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"  wrote {path.relative_to(Path(__file__).parents[2])}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dedup benchmark: S3+SQLite vs DynamoDB")
    parser.add_argument(
        "--backend",
        choices=["sqlite", "dynamodb", "athena", "duckdb", "both"],
        default="both",
        help="Which backend(s) to run (default: both)",
    )
    args = parser.parse_args()

    batch_uris, seed_uris = load_all_mock_data()
    table_sizes = [ts for ts in TABLE_SIZES if ts in seed_uris]

    timestamp = get_current_timestamp()
    out_dir = DATA_DIR / timestamp

    sqlite_results: dict = {}
    dynamodb_results: dict = {}
    athena_results: dict = {}
    duckdb_results: dict = {}

    if args.backend in ("sqlite", "both"):
        print("\n=== S3 + SQLite ===")
        sqlite_backend = SQLiteBackend()
        sqlite_results = run_backend(
            "sqlite",
            sqlite_backend,
            batch_uris,
            seed_uris,
            table_sizes=table_sizes,
            out_dir=out_dir,
        )

    if args.backend in ("dynamodb", "both"):
        print("\n=== DynamoDB ===")
        dynamodb_backend = DynamoDBBackend()
        dynamodb_results = run_backend(
            "dynamodb",
            dynamodb_backend,
            batch_uris,
            seed_uris,
            table_sizes=table_sizes,
            out_dir=out_dir,
        )

    if args.backend == "duckdb":
        print("\n=== S3 + DuckDB ===")
        duckdb_backend = DuckDBBackend()
        duckdb_results = run_backend(
            "duckdb",
            duckdb_backend,
            batch_uris,
            seed_uris,
            table_sizes=table_sizes,
            out_dir=out_dir,
        )

    if args.backend == "athena":
        print("\n=== S3 + Athena ===")
        athena_backend = AthenaBackend()
        athena_results = run_backend(
            "athena",
            athena_backend,
            batch_uris,
            seed_uris,
            table_sizes=table_sizes,
            out_dir=out_dir,
        )

    print_results_table(
        sqlite_results, dynamodb_results, athena_results, duckdb_results, table_sizes=table_sizes
    )

    if sqlite_results and dynamodb_results:
        console.print("\nBuilding cross-backend metrics...")
        metrics = build_metrics(sqlite_results, dynamodb_results, table_sizes=table_sizes)
        write_json(out_dir / "metrics.json", metrics)
        console.print(f"\n[bold]Recommendation:[/bold] {metrics['recommendation']}")

    import boto3  # type: ignore[import-untyped]

    metadata = {
        "timestamp": timestamp,
        "aws_region": boto3.session.Session().region_name,
        "dynamodb_table_name": "lab-data-integrations-dedup-experiment-seen-ids",
        "s3_bucket_name": "lab-data-integrations-dedup-experiment-use2",
        "s3_sqlite_key": "dedup-experiment/seen.db",
        "n_runs_per_combination": N_RUNS,
        "warmup_runs": WARMUP,
        "batch_sizes_tested": BATCH_SIZES,
        "table_sizes_tested": table_sizes,
        "python_version": sys.version,
    }
    write_json(out_dir / "metadata.json", metadata)
    print(f"\nResults written to experiments/dedup_comparison_2026_06_12/data/{timestamp}/")


if __name__ == "__main__":
    main()
