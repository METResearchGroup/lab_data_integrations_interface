"""Latency aggregation and cost estimation for the dedup benchmark.

Run from repo root:
    PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/metrics.py
"""

from __future__ import annotations

from typing import Any


def compute_latency_stats(values_ms: list[float]) -> dict[str, float]:
    if not values_ms:
        return {"ms": 0.0}
    return {"ms": round(values_ms[0], 3)}


def aggregate_run_results(runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "check_latency": compute_latency_stats([r["check_ms"] for r in runs]),
        "write_latency": compute_latency_stats([r["write_ms"] for r in runs]),
        "end_to_end_latency": compute_latency_stats([r["end_to_end_ms"] for r in runs]),
        "http_call_count": runs[0]["http_calls"] if runs else 0,
        "peak_rss_mb": round(max(r["peak_rss_mb"] for r in runs), 2),
        "n_runs": len(runs),
    }


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

# S3 on-demand pricing (us-east-2)
_S3_GET_PER_REQUEST = 0.0004 / 1000  # $0.0004 per 1,000 GETs
_S3_PUT_PER_REQUEST = 0.005 / 1000  # $0.005 per 1,000 PUTs
_S3_STORAGE_PER_GB_MONTH = 0.023

# DynamoDB on-demand pricing (us-east-2, eventually consistent)
_DYNAMO_RRU_PER_MILLION = 0.25  # $0.25 per million RRUs
_DYNAMO_WRU_PER_MILLION = 1.25  # $1.25 per million WRUs
_DYNAMO_STORAGE_PER_GB_MONTH = 0.25

# Each BatchGetItem on items < 4KB = 0.5 RRU (eventually consistent)
_RRU_PER_ITEM = 0.5
# Each PutItem on items < 1KB = 1 WRU
_WRU_PER_ITEM = 1.0

# Approximate bytes per URI row in SQLite (uri ~60 bytes + overhead)
_BYTES_PER_URI_SQLITE = 80
# Approximate bytes per URI item in DynamoDB
_BYTES_PER_URI_DYNAMO = 80


def estimate_sqlite_cost_per_1000_runs(
    *,
    table_size_uris: int,
) -> dict[str, float]:
    storage_gb = (table_size_uris * _BYTES_PER_URI_SQLITE) / (1024**3)
    storage_cost = storage_gb * _S3_STORAGE_PER_GB_MONTH

    # Per run: 1 GET (download) + 1 PUT (upload)
    get_cost_per_1000 = 1000 * _S3_GET_PER_REQUEST
    put_cost_per_1000 = 1000 * _S3_PUT_PER_REQUEST

    return {
        "storage_per_month_usd": round(storage_cost, 6),
        "get_cost_per_1000_runs_usd": round(get_cost_per_1000, 6),
        "put_cost_per_1000_runs_usd": round(put_cost_per_1000, 6),
        "total_per_1000_runs_usd": round(get_cost_per_1000 + put_cost_per_1000, 6),
    }


def estimate_dynamodb_cost_per_1000_runs(
    *,
    table_size_uris: int,
    batch_size_uris: int,
    avg_new_uris_per_run: int,
) -> dict[str, float]:
    storage_gb = (table_size_uris * _BYTES_PER_URI_DYNAMO) / (1024**3)
    storage_cost = storage_gb * _DYNAMO_STORAGE_PER_GB_MONTH

    # Reads: batch_size items × 0.5 RRU each
    rrus_per_run = batch_size_uris * _RRU_PER_ITEM
    read_cost_per_1000 = (rrus_per_run * 1000) / 1_000_000 * _DYNAMO_RRU_PER_MILLION

    # Writes: avg_new_uris_per_run × 1 WRU each
    wrus_per_run = avg_new_uris_per_run * _WRU_PER_ITEM
    write_cost_per_1000 = (wrus_per_run * 1000) / 1_000_000 * _DYNAMO_WRU_PER_MILLION

    return {
        "storage_per_month_usd": round(storage_cost, 6),
        "read_cost_per_1000_runs_usd": round(read_cost_per_1000, 6),
        "write_cost_per_1000_runs_usd": round(write_cost_per_1000, 6),
        "total_per_1000_runs_usd": round(read_cost_per_1000 + write_cost_per_1000, 6),
    }


def compute_scale_degradation(
    results: dict[str, Any],
    *,
    batch_size: int,
) -> float:
    key_empty = f"batch_{batch_size}_table_0"
    key_100k = f"batch_{batch_size}_table_100000"
    if key_empty not in results or key_100k not in results:
        return float("nan")
    latency_empty = results[key_empty]["check_latency"]["ms"]
    latency_100k = results[key_100k]["check_latency"]["ms"]
    if latency_empty == 0:
        return float("nan")
    return round(latency_100k / latency_empty, 3)
