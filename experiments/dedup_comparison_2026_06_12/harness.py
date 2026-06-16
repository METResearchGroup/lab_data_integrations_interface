"""Benchmark harness: timing + memory measurement for a single dedup cycle.

Run from repo root:
    PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/harness.py
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from experiments.database_experiments_2026_05_23.metrics import ResourceMonitor
from experiments.dedup_comparison_2026_06_12.metrics import aggregate_run_results


class DeduplicationBackend(Protocol):
    def seed(self, uris: list[str]) -> None: ...
    def check(self, uris: list[str]) -> tuple[list[str], int]: ...
    def write(self, uris: list[str]) -> int: ...
    def cleanup(self, uris: list[str]) -> None: ...
    def clear_all(self) -> None: ...


def run_one_iteration(
    backend: DeduplicationBackend,
    batch_uris: list[str],
) -> dict[str, Any]:
    monitor = ResourceMonitor()
    monitor.start()

    check_start = time.perf_counter()
    new_uris, check_calls = backend.check(batch_uris)
    check_ms = (time.perf_counter() - check_start) * 1000.0

    resources = monitor.stop()

    write_start = time.perf_counter()
    write_calls = backend.write(new_uris)
    write_ms = (time.perf_counter() - write_start) * 1000.0

    backend.cleanup(new_uris)

    return {
        "check_ms": check_ms,
        "write_ms": write_ms,
        "end_to_end_ms": check_ms + write_ms,
        "http_calls": check_calls + write_calls,
        "peak_rss_mb": resources["peak_rss_mb"],
        "n_new_uris": len(new_uris),
    }


def run_benchmark(
    backend: DeduplicationBackend,
    batch_uris: list[str],
    *,
    n_runs: int,
    warmup: int,
    label: str,
) -> dict[str, Any]:
    measured: list[dict[str, Any]] = []
    for i in range(warmup + n_runs):
        tag = f"warmup {i + 1}/{warmup}" if i < warmup else f"run {i - warmup + 1}/{n_runs}"
        print(f"      [{label}] {tag}", end="\r", flush=True)
        result = run_one_iteration(backend, batch_uris)
        if i >= warmup:
            measured.append(result)

    print(f"      [{label}] {n_runs} runs complete" + " " * 20)
    return aggregate_run_results(measured)
