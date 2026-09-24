"""Phase 2 -- replay a capture through both write paths and price every operation.

Order matters at startup: the meter patches ``botocore.session.Session`` and only
sessions constructed afterwards carry the handlers, so ``METER.install()`` runs
before anything touches AWS.

Usage:
    python -m experimentation.iceberg.run_experiment --capture data/captures/<file>.jsonl.gz
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from experimentation.iceberg import constants
from experimentation.iceberg.s3_meter import METER

# Installed before any other project import can build an AWS client.
METER.install()

from experimentation.iceberg import catalog as catalog_module  # noqa: E402
from experimentation.iceberg import iceberg_writer, maintenance, replay  # noqa: E402
from experimentation.iceberg.raw_writer import RawWriter  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "data" / "results"


def _new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


@dataclass
class IngestResult:
    """Totals accumulated while replaying the capture through both write paths."""

    rows_by_type: dict[str, int]
    fallback_delete_rows: int
    fallback_malformed_rows: int
    batches: int
    seconds: float

    @property
    def total_rows(self) -> int:
        return sum(self.rows_by_type.values())


def _count_fallbacks(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Split `createdAt` fallbacks into (delete events, genuinely skewed).

    A delete carries no record body, so it structurally has no `createdAt`.
    Lumping those in with bad client timestamps overstates the data-quality
    problem by an order of magnitude.
    """
    deletes = malformed = 0
    for row in rows:
        if not row["created_at_fallback"]:
            continue
        if row["operation"] == "delete":
            deletes += 1
        else:
            malformed += 1
    return deletes, malformed


def _write_one(
    tables: dict[str, Any],
    raw_writer: RawWriter | None,
    record_type: str,
    rows: list[dict[str, Any]],
    batch_index: int,
) -> None:
    """Send one record type's slice of a batch down both write paths."""
    if raw_writer is not None:
        with METER.phase(constants.PHASE_RAW_WRITE):
            raw_writer.write_batch(record_type, rows, batch_index)
    with METER.phase(constants.PHASE_ICEBERG_APPEND):
        iceberg_writer.append_batch(tables[record_type], rows)


def _ingest(
    capture_path: Path,
    tables: dict[str, Any],
    raw_writer: RawWriter | None,
    flush_seconds: int,
    max_batches: int | None,
) -> IngestResult:
    """Replay the capture, one flush batch at a time."""
    rows_by_type = {rt: 0 for rt in constants.RECORD_TYPES}
    fallback_deletes = fallback_malformed = batches = 0
    started = time.perf_counter()

    events = replay.iter_events(capture_path)
    for batch_index, buffers in replay.iter_batches(events, flush_seconds=flush_seconds):
        if max_batches is not None and batch_index >= max_batches:
            break
        batches += 1
        batch_rows = sum(len(rows) for rows in buffers.values())
        print(
            f"batch {batch_index:>3}  {batch_rows:>7,} rows  "
            + ", ".join(f"{rt}={len(rows):,}" for rt, rows in buffers.items())
        )

        for record_type, rows in buffers.items():
            rows_by_type[record_type] += len(rows)
            deletes, malformed = _count_fallbacks(rows)
            fallback_deletes += deletes
            fallback_malformed += malformed
            _write_one(tables, raw_writer, record_type, rows, batch_index)

    return IngestResult(
        rows_by_type=rows_by_type,
        fallback_delete_rows=fallback_deletes,
        fallback_malformed_rows=fallback_malformed,
        batches=batches,
        seconds=time.perf_counter() - started,
    )


def _table_state(tables: dict[str, Any]) -> dict[str, Any]:
    return {
        rt: iceberg_writer.table_file_stats(table)
        | {"snapshots": iceberg_writer.snapshot_count(table)}
        for rt, table in tables.items()
    }


def _compact_all(tables: dict[str, Any]) -> dict[str, Any]:
    print("compacting, collapsing lifecycles, dropping tombstones...")
    results: dict[str, Any] = {}
    with METER.phase(constants.PHASE_COMPACT_DEDUP):
        for record_type, table in tables.items():
            result = maintenance.compact_table(table)
            results[record_type] = result
            if result.get("skipped"):
                continue
            print(
                f"  {record_type:<9} {result['file_count_before']:>3} -> "
                f"{result['file_count_after']:>3} files, "
                f"{result['redelivered_duplicates']:,} redelivered, "
                f"{result['lifecycle_collapses']:,} lifecycle, "
                f"{result['tombstones_dropped']:,} tombstones "
                f"({result['tombstone_pct']:.1f}%)"
            )
    return results


def _expire_all(tables: dict[str, Any]) -> dict[str, Any]:
    print("\nexpiring snapshots and sweeping orphans...")
    results: dict[str, Any] = {}
    with METER.phase(constants.PHASE_EXPIRE_METADATA):
        for record_type, table in tables.items():
            expired = maintenance.expire_snapshots(table)
            swept = maintenance.sweep_orphans(table)
            results[record_type] = expired | swept
            print(
                f"  {record_type:<9} {expired['expired']:>2} snapshots expired, "
                f"{swept['orphans_deleted']:>3} orphans deleted "
                f"({swept['orphan_bytes_reclaimed'] / 1024 / 1024:.1f} MiB)"
            )
    return results


def run(
    capture_path: Path,
    run_id: str,
    flush_seconds: int,
    max_batches: int | None = None,
    include_raw: bool = True,
) -> dict[str, Any]:
    """Execute all four measured phases against one capture file."""
    print(f"run_id       {run_id}")
    print(f"capture      {capture_path}")
    print(f"flush window {flush_seconds}s")
    print(f"warehouse    {catalog_module.warehouse_uri(run_id)}\n")

    catalog = catalog_module.build_catalog(run_id)
    tables = catalog_module.create_tables(catalog, run_id)
    print(f"created {len(tables)} Glue tables in `{constants.GLUE_DATABASE}`\n")

    raw_writer = RawWriter(run_id) if include_raw else None
    ingest = _ingest(capture_path, tables, raw_writer, flush_seconds, max_batches)
    print(
        f"\ningested {ingest.total_rows:,} rows in {ingest.batches} batches "
        f"({ingest.seconds:.1f}s)\n"
    )

    pre_maintenance = _table_state(tables)
    compaction = _compact_all(tables)
    expiry = _expire_all(tables)
    post_maintenance = _table_state(tables)

    return {
        "run_id": run_id,
        "capture": str(capture_path),
        "flush_seconds": flush_seconds,
        "batches": ingest.batches,
        "ingest_seconds": ingest.seconds,
        "rows_by_type": ingest.rows_by_type,
        "total_rows": ingest.total_rows,
        "created_at_fallback_delete_rows": ingest.fallback_delete_rows,
        "created_at_fallback_malformed_rows": ingest.fallback_malformed_rows,
        "raw_bytes_written": raw_writer.bytes_written if raw_writer else 0,
        "raw_objects_written": raw_writer.objects_written if raw_writer else 0,
        "pre_maintenance": pre_maintenance,
        "post_maintenance": post_maintenance,
        "compaction": compaction,
        "expiry": expiry,
        "warehouse": catalog_module.warehouse_uri(run_id),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a Jetstream capture into S3 + Iceberg.")
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--flush-seconds", type=int, default=constants.DEFAULT_FLUSH_SECONDS)
    parser.add_argument("--max-batches", type=int, default=None)
    parser.add_argument("--skip-raw", action="store_true", help="Skip the non-Iceberg baseline.")
    args = parser.parse_args()

    run_id = args.run_id or _new_run_id()
    results = run(
        capture_path=args.capture,
        run_id=run_id,
        flush_seconds=args.flush_seconds,
        max_batches=args.max_batches,
        include_raw=not args.skip_raw,
    )

    # Import here so the report module cannot pull in botocore before install().
    from experimentation.iceberg import report

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stats = METER.summarize()

    results_path = RESULTS_DIR / f"{run_id}-results.json"
    results_path.write_text(
        json.dumps(results | {"phases": report.serialize_stats(stats)}, indent=2, default=str)
    )

    report_path = RESULTS_DIR / f"{run_id}-report.md"
    report_text = report.render(results, stats)
    report_path.write_text(report_text)

    calls_path = RESULTS_DIR / f"{run_id}-calls.csv"
    report.write_call_log(METER.records, calls_path)

    print(f"\n{report_text}")
    print(f"\nwrote {results_path}")
    print(f"wrote {report_path}")
    print(f"wrote {calls_path}")


if __name__ == "__main__":
    main()
