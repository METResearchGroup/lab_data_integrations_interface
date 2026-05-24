"""Shared multi-threaded benchmark harness with warm-up and measured phases.

Run from repo root with PYTHONPATH=.
"""

from __future__ import annotations

import argparse
import random
import sys
import threading
from typing import Protocol

from experiments.database_experiments_2026_05_23.metrics import (
    ResourceMonitor,
    compute_latency_stats,
)
from experiments.database_experiments_2026_05_23.queries import QUERY_SPECS, QueryId


class QueryRunner(Protocol):
    def run_query(self, query_id: QueryId, *, author_id: str | None) -> None: ...


def run_benchmark_for_query(
    runner: QueryRunner,
    query_id: QueryId,
    *,
    threads: int,
    iterations: int,
    warmup: int,
    author_ids: list[str],
    rng: random.Random,
) -> tuple[list[float], dict]:
    latencies_ms: list[float] = []
    lock = threading.Lock()

    def worker() -> None:
        local_latencies: list[float] = []
        for _ in range(warmup):
            author_id = rng.choice(author_ids) if author_ids else None
            runner.run_query(query_id, author_id=author_id)

        for _ in range(iterations):
            author_id = rng.choice(author_ids) if author_ids else None
            start = __import__("time").perf_counter()
            runner.run_query(query_id, author_id=author_id)
            elapsed_ms = (__import__("time").perf_counter() - start) * 1000.0
            local_latencies.append(elapsed_ms)

        with lock:
            latencies_ms.extend(local_latencies)

    monitor = ResourceMonitor()
    monitor.start()

    thread_objs = [threading.Thread(target=worker) for _ in range(threads)]
    for thread in thread_objs:
        thread.start()
    for thread in thread_objs:
        thread.join()

    resource_stats = monitor.stop()
    return latencies_ms, resource_stats


def run_benchmark(
    runner: QueryRunner,
    *,
    threads: int,
    iterations: int,
    warmup: int,
    author_ids: list[str],
    seed: int = 42,
) -> tuple[dict[str, dict], dict]:
    rng = random.Random(seed)
    query_results: dict[str, dict] = {}
    total_resources = {
        "cpu_time_seconds": 0.0,
        "peak_rss_bytes": 0,
        "sustained_rss_bytes": 0,
    }

    for spec in QUERY_SPECS:
        latencies_ms, resources = run_benchmark_for_query(
            runner,
            spec.query_id,
            threads=threads,
            iterations=iterations,
            warmup=warmup,
            author_ids=author_ids if spec.requires_author_id else [],
            rng=rng,
        )
        stats = compute_latency_stats(latencies_ms, threads=threads)
        query_results[spec.query_id.value] = {
            "query_id": spec.query_id.value,
            "category": spec.category.value,
            "description": spec.description,
            **stats,
        }
        total_resources["cpu_time_seconds"] += resources["cpu_time_seconds"]
        total_resources["peak_rss_bytes"] = max(
            total_resources["peak_rss_bytes"], resources["peak_rss_bytes"]
        )
        total_resources["sustained_rss_bytes"] = max(
            total_resources["sustained_rss_bytes"], resources["sustained_rss_bytes"]
        )

    total_resources["peak_rss_mb"] = round(total_resources["peak_rss_bytes"] / (1024 * 1024), 2)
    total_resources["sustained_rss_mb"] = round(
        total_resources["sustained_rss_bytes"] / (1024 * 1024), 2
    )
    return query_results, total_resources


class _NoOpRunner:
    def run_query(self, query_id: QueryId, *, author_id: str | None) -> None:
        _ = (query_id, author_id)


def self_check() -> None:
    sample = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    stats = compute_latency_stats(sample, threads=2)
    assert stats["p50_ms"] == 5.5
    assert stats["executions"] == 10

    runner = _NoOpRunner()
    latencies, _resources = run_benchmark_for_query(
        runner,
        QueryId.POSTS_TODAY_LIMIT_100,
        threads=2,
        iterations=3,
        warmup=2,
        author_ids=[],
        rng=random.Random(0),
    )
    expected_executions = 2 * 3
    assert len(latencies) == expected_executions, (
        f"Expected {expected_executions} measured executions, got {len(latencies)}"
    )
    print(f"p50={stats['p50_ms']}, p90={stats['p90_ms']}, p99={stats['p99_ms']}")
    print(f"Measured executions={len(latencies)} (threads=2 x iterations=3)")
    print("HARNESS SELF-CHECK PASS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark harness utilities")
    parser.add_argument("--self-check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.self_check:
        self_check()
        return
    print("No action specified. Use --self-check", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
