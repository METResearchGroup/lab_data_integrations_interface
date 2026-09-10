"""Render the measured call log into a markdown report and a raw CSV."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from experimentation.iceberg import constants
from experimentation.iceberg.s3_meter import CallRecord, PhaseStats

SECONDS_PER_DAY = 86_400
DAYS_PER_MONTH = 30


def serialize_stats(stats: dict[str, PhaseStats]) -> dict[str, Any]:
    """Flatten PhaseStats into JSON-safe dicts."""
    return {
        phase: {
            "wall_seconds": entry.wall_seconds,
            "calls": entry.calls,
            "attempts": entry.attempts,
            "request_bytes": entry.request_bytes,
            "response_bytes": entry.response_bytes,
            "cost_usd": entry.cost_usd,
            "by_tier": dict(entry.by_tier),
            "by_operation": dict(entry.by_operation),
            "by_key_class": dict(entry.by_key_class),
            "by_key_class_operation": {k: dict(v) for k, v in entry.by_key_class_operation.items()},
            "latency_p50_ms": entry.percentile(50),
            "latency_p95_ms": entry.percentile(95),
            "latency_p99_ms": entry.percentile(99),
            "latency_max_ms": max(entry.latencies_ms) if entry.latencies_ms else 0.0,
        }
        for phase, entry in stats.items()
    }


def write_call_log(records: list[CallRecord], path: Path) -> None:
    """Dump every individual API call, for slicing outside this report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "phase",
                "service",
                "operation",
                "tier",
                "key_class",
                "key",
                "request_bytes",
                "response_bytes",
                "duration_ms",
                "status",
            ]
        )
        for record in records:
            writer.writerow(
                [
                    record.phase,
                    record.service,
                    record.operation,
                    record.tier,
                    record.key_class,
                    record.key,
                    record.request_bytes,
                    record.response_bytes,
                    f"{record.duration_ms:.2f}",
                    record.status,
                ]
            )


def _mib(value: float) -> str:
    return f"{value / 1024 / 1024:.2f}"


def _phase_table(stats: dict[str, PhaseStats]) -> list[str]:
    lines = [
        "| Phase | Wall (s) | Calls | PUT-tier | GET-tier | DELETE | Glue | Retries | Cost (USD) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for phase in constants.PHASES:
        entry = stats.get(phase)
        if entry is None:
            continue
        retries = max(0, entry.attempts - entry.calls)
        lines.append(
            f"| `{phase}` | {entry.wall_seconds:.1f} | {entry.calls:,} | "
            f"{entry.by_tier['put']:,} | {entry.by_tier['get']:,} | "
            f"{entry.by_tier['delete']:,} | {entry.by_tier['glue']:,} | "
            f"{retries:,} | ${entry.cost_usd:.6f} |"
        )
    return lines


def _key_class_table(stats: dict[str, PhaseStats]) -> list[str]:
    lines = [
        "| Phase | Object class | Calls | Operations |",
        "|---|---|---:|---|",
    ]
    for phase in constants.PHASES:
        entry = stats.get(phase)
        if entry is None:
            continue
        for key_class, count in sorted(entry.by_key_class.items(), key=lambda kv: -kv[1]):
            ops = entry.by_key_class_operation.get(key_class, {})
            detail = ", ".join(f"{op} x{n}" for op, n in sorted(ops.items(), key=lambda kv: -kv[1]))
            lines.append(f"| `{phase}` | {key_class} | {count:,} | {detail} |")
    return lines


def _latency_table(stats: dict[str, PhaseStats]) -> list[str]:
    lines = [
        "| Phase | p50 (ms) | p95 (ms) | p99 (ms) | max (ms) | Total AWS time (s) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for phase in constants.PHASES:
        entry = stats.get(phase)
        if entry is None or not entry.latencies_ms:
            continue
        lines.append(
            f"| `{phase}` | {entry.percentile(50):.0f} | {entry.percentile(95):.0f} | "
            f"{entry.percentile(99):.0f} | {max(entry.latencies_ms):.0f} | "
            f"{sum(entry.latencies_ms) / 1000:.1f} |"
        )
    return lines


def _amplification_section(results: dict[str, Any], stats: dict[str, PhaseStats]) -> list[str]:
    """Compare the Iceberg path against the raw-Parquet control."""
    raw = stats.get(constants.PHASE_RAW_WRITE)
    ice = stats.get(constants.PHASE_ICEBERG_APPEND)
    if raw is None or ice is None:
        return ["_Baseline skipped, no comparison available._"]

    raw_puts = raw.by_tier["put"]
    ice_puts = ice.by_tier["put"]
    logical = results.get("raw_bytes_written", 0)
    ice_bytes = ice.request_bytes

    lines = [
        "| Metric | Raw Parquet | Iceberg | Ratio |",
        "|---|---:|---:|---:|",
        f"| PUT-tier requests | {raw_puts:,} | {ice_puts:,} | {ice_puts / raw_puts:.2f}x |"
        if raw_puts
        else f"| PUT-tier requests | {raw_puts:,} | {ice_puts:,} | n/a |",
        f"| Total AWS calls | {raw.calls:,} | {ice.calls:,} | "
        + (f"{ice.calls / raw.calls:.2f}x |" if raw.calls else "n/a |"),
        f"| Bytes uploaded | {_mib(raw.request_bytes)} MiB | {_mib(ice_bytes)} MiB | "
        + (f"{ice_bytes / raw.request_bytes:.2f}x |" if raw.request_bytes else "n/a |"),
        f"| Wall time | {raw.wall_seconds:.1f}s | {ice.wall_seconds:.1f}s | "
        + (f"{ice.wall_seconds / raw.wall_seconds:.2f}x |" if raw.wall_seconds else "n/a |"),
        f"| Cost | ${raw.cost_usd:.6f} | ${ice.cost_usd:.6f} | "
        + (f"{ice.cost_usd / raw.cost_usd:.2f}x |" if raw.cost_usd else "n/a |"),
    ]

    if logical:
        lines += [
            "",
            f"**Write amplification.** {_mib(logical)} MiB of logical Parquet produced "
            f"{_mib(ice_bytes)} MiB of Iceberg uploads "
            f"({ice_bytes / logical:.2f}x) across {ice_puts:,} PUT-tier requests.",
        ]
    return lines


def _extrapolation(results: dict[str, Any], stats: dict[str, PhaseStats]) -> list[str]:
    """Project the measured run out to a day and a month at the same rate."""
    capture_seconds = results["batches"] * results["flush_seconds"]
    if capture_seconds <= 0:
        return []

    total_cost = sum(entry.cost_usd for entry in stats.values())
    scale_day = SECONDS_PER_DAY / capture_seconds

    ingest_cost = sum(
        stats[phase].cost_usd
        for phase in (constants.PHASE_RAW_WRITE, constants.PHASE_ICEBERG_APPEND)
        if phase in stats
    )
    maintenance_cost = total_cost - ingest_cost

    rows_per_day = results["total_rows"] * scale_day

    return [
        f"Measured window covers **{capture_seconds / 60:.1f} minutes** of firehose "
        f"({results['total_rows']:,} rows, {results['total_rows'] / capture_seconds:,.0f} rows/s).",
        "",
        "| Horizon | Rows | Ingest cost | Maintenance cost | Total |",
        "|---|---:|---:|---:|---:|",
        f"| Measured run | {results['total_rows']:,} | ${ingest_cost:.4f} | "
        f"${maintenance_cost:.4f} | ${total_cost:.4f} |",
        f"| 24 hours | {rows_per_day:,.0f} | ${ingest_cost * scale_day:.2f} | "
        f"${maintenance_cost * scale_day:.2f} | ${total_cost * scale_day:.2f} |",
        f"| 30 days | {rows_per_day * DAYS_PER_MONTH:,.0f} | "
        f"${ingest_cost * scale_day * DAYS_PER_MONTH:.2f} | "
        f"${maintenance_cost * scale_day * DAYS_PER_MONTH:.2f} | "
        f"${total_cost * scale_day * DAYS_PER_MONTH:.2f} |",
        "",
        "_Maintenance is extrapolated at the same per-window frequency as the measured "
        "run. In production you would compact far less often than every flush, so treat "
        "this as an upper bound on the maintenance column._",
    ]


def _compaction_section(results: dict[str, Any]) -> list[str]:
    lines = [
        "| Table | Files before | Files after | Rows before | Rows after "
        "| Redelivered dupes | Lifecycle collapses | Tombstones dropped "
        "| Bytes before | Bytes after |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for record_type in constants.RECORD_TYPES:
        entry = results["compaction"].get(record_type, {})
        if entry.get("skipped", True):
            continue
        lines.append(
            f"| {record_type} | {entry['file_count_before']} | {entry['file_count_after']} | "
            f"{entry['rows_before']:,} | {entry['rows_after']:,} | "
            f"{entry['redelivered_duplicates']:,} | "
            f"{entry['lifecycle_collapses']:,} | "
            f"{entry['tombstones_dropped']:,} ({entry['tombstone_pct']:.1f}%) | "
            f"{_mib(entry['bytes_before'])} MiB | {_mib(entry['bytes_after'])} MiB |"
        )

    total_redelivered = sum(
        e.get("redelivered_duplicates", 0)
        for e in results["compaction"].values()
        if not e.get("skipped", True)
    )
    lines += [
        "",
        f"**Redelivered duplicates across all tables: {total_redelivered:,}.** "
        "A redelivered duplicate is the identical event twice -- same `uri` *and* same "
        "`cid`. Lifecycle collapses are different: several distinct events about one "
        "record (create then delete, create then update), each with its own `cid`. "
        "Only the first is a stream defect; the second is a record's history being "
        "materialised into current state.",
        "",
        "Tombstones are `delete` rows, which carry no record body. They are dropped at "
        "compaction. Note this only cancels a create that is in the same table -- a "
        "delete of a record written before this table existed has nothing to reconcile "
        "against and is simply discarded.",
    ]
    return lines


def _expiry_section(results: dict[str, Any]) -> list[str]:
    lines = [
        "| Table | Snapshots before | after | Objects listed | Orphans deleted | Reclaimed |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for record_type in constants.RECORD_TYPES:
        entry = results["expiry"].get(record_type, {})
        if not entry:
            continue
        lines.append(
            f"| {record_type} | {entry['snapshots_before']} | {entry['snapshots_after']} | "
            f"{entry['objects_listed']} | {entry['orphans_deleted']} | "
            f"{_mib(entry['orphan_bytes_reclaimed'])} MiB |"
        )
    return lines


def render(results: dict[str, Any], stats: dict[str, PhaseStats]) -> str:
    """Assemble the full markdown report."""
    deletes = results["created_at_fallback_delete_rows"]
    skewed = results["created_at_fallback_malformed_rows"]
    total = results["total_rows"] or 1

    sections: list[str] = [
        f"# Iceberg write-amplification experiment -- `{results['run_id']}`",
        "",
        f"- Capture: `{results['capture']}`",
        f"- Warehouse: `{results['warehouse']}`",
        f"- Flush window: {results['flush_seconds']}s -> {results['batches']} batches per table",
        f"- Rows: {results['total_rows']:,} "
        + ", ".join(f"{rt}={n:,}" for rt, n in results["rows_by_type"].items()),
        f"- `createdAt` fallbacks: {deletes + skewed:,} rows partitioned by ingest time, of which",
        f"  - {deletes:,} ({deletes / total * 100:.2f}%) are `delete` events, which carry no "
        "record body and therefore have no `createdAt` at all -- structural, not a data problem",
        f"  - {skewed:,} ({skewed / total * 100:.2f}%) parse cleanly but sit more than "
        f"{constants.MAX_CREATED_AT_SKEW_SECONDS // 3600}h from the broker timestamp. These are "
        "mostly archive-import bots stamping genuine historical dates; the skew rule rewrites them "
        "to keep one bot from opening a daily partition per historical date it touches",
        "",
        "## Cost and request counts by phase",
        "",
        *_phase_table(stats),
        "",
        "## Where the requests go",
        "",
        *_key_class_table(stats),
        "",
        "## Latency",
        "",
        *_latency_table(stats),
        "",
        "## Iceberg vs. raw Parquet",
        "",
        *_amplification_section(results, stats),
        "",
        "## Compaction and deduplication",
        "",
        *_compaction_section(results),
        "",
        "## Snapshot expiry and orphan cleanup",
        "",
        *_expiry_section(results),
        "",
        "## Extrapolation",
        "",
        *_extrapolation(results, stats),
        "",
        "---",
        "",
        "Pricing model (us-east-2): PUT/LIST $0.005/1k, GET $0.0004/1k, DELETE free, "
        "Glue $1/100k requests. Storage is not included in the per-phase cost column.",
    ]
    return "\n".join(sections)
