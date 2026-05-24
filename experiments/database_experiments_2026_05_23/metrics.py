"""Latency aggregation and resource monitoring for benchmark runs.

Run from repo root with PYTHONPATH=.
"""

from __future__ import annotations

import statistics
import threading
import time
from dataclasses import dataclass, field

import psutil


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * (pct / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def compute_latency_stats(latencies_ms: list[float], *, threads: int) -> dict:
    if not latencies_ms:
        return {
            "p50_ms": 0.0,
            "p90_ms": 0.0,
            "p99_ms": 0.0,
            "mean_ms": 0.0,
            "stddev_ms": 0.0,
            "qps": 0.0,
            "executions": 0,
            "threads": threads,
        }

    total_seconds = sum(latencies_ms) / 1000.0
    qps = len(latencies_ms) / total_seconds if total_seconds > 0 else 0.0
    return {
        "p50_ms": percentile(latencies_ms, 50),
        "p90_ms": percentile(latencies_ms, 90),
        "p99_ms": percentile(latencies_ms, 99),
        "mean_ms": statistics.mean(latencies_ms),
        "stddev_ms": statistics.pstdev(latencies_ms) if len(latencies_ms) > 1 else 0.0,
        "qps": qps,
        "executions": len(latencies_ms),
        "threads": threads,
    }


@dataclass
class ResourceMonitor:
    process: psutil.Process = field(default_factory=lambda: psutil.Process())
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    _cpu_times_start: tuple[float, float] | None = None
    _peak_rss_bytes: int = 0
    _samples: list[int] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> None:
        self._cpu_times_start = self.process.cpu_times()[:2]
        self._peak_rss_bytes = self.process.memory_info().rss
        self._samples = [self._peak_rss_bytes]
        self._stop.clear()
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def _sample_loop(self) -> None:
        while not self._stop.wait(0.05):
            try:
                rss = self.process.memory_info().rss
            except psutil.Error:
                continue
            with self._lock:
                self._samples.append(rss)
                self._peak_rss_bytes = max(self._peak_rss_bytes, rss)

    def stop(self) -> dict:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

        cpu_time_seconds = 0.0
        if self._cpu_times_start is not None:
            end = self.process.cpu_times()[:2]
            cpu_time_seconds = (end[0] - self._cpu_times_start[0]) + (
                end[1] - self._cpu_times_start[1]
            )

        with self._lock:
            sustained_rss_bytes = int(statistics.mean(self._samples)) if self._samples else 0
            peak_rss_bytes = self._peak_rss_bytes

        return {
            "cpu_time_seconds": round(cpu_time_seconds, 4),
            "peak_rss_bytes": peak_rss_bytes,
            "peak_rss_mb": round(peak_rss_bytes / (1024 * 1024), 2),
            "sustained_rss_bytes": sustained_rss_bytes,
            "sustained_rss_mb": round(sustained_rss_bytes / (1024 * 1024), 2),
        }


class QueryTimer:
    def __init__(self) -> None:
        self._start: float | None = None

    def __enter__(self) -> QueryTimer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    @property
    def elapsed_ms(self) -> float:
        if self._start is None:
            return 0.0
        return (time.perf_counter() - self._start) * 1000.0
