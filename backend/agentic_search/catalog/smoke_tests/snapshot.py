"""Build a snapshot from the real Glue tables and print it. Read-only; needs AWS credentials.

PYTHONPATH=. uv run python backend/agentic_search/catalog/smoke_tests/snapshot.py
"""

import time
from datetime import timedelta

from backend.agentic_search.catalog.snapshot import build_snapshot
from backend.agentic_search.models import CatalogSnapshot
from bluesky_ingestion_jetstream.aws.catalog import build_catalog, load_tables
from bluesky_ingestion_jetstream.aws.constants import PARTITION_FIELD_NAME


def print_snapshot(snapshot: CatalogSnapshot) -> None:
    """What the snapshot holds -- this is what the pipeline sees."""

    print("\n" + "=" * 78)
    print("SNAPSHOT")
    print("=" * 78)

    for table in snapshot.tables:
        rows = f"{table.row_count:,}" if table.row_count is not None else "-"
        print(f"\n{table.database}.{table.name}  ({table.description})")
        print(f"  coverage : {table.earliest_day} -> {table.latest_day}")
        print(f"  rows     : {rows}")
        print(f"  columns  : {len(table.columns)}")
        for column in table.columns:
            print(f"      {column.name:<18} {column.type:<14} {column.description or '-'}")

    total = sum(table.row_count or 0 for table in snapshot.tables)
    print(f"\ncaptured_at: {snapshot.captured_at.isoformat()}")
    print(f"total rows across tables: {total:,}")


def print_partition_detail() -> None:
    """What the snapshot summarizes away: gaps, deletes, file counts, size."""

    print("\n" + "=" * 78)
    print("PARTITION DETAIL (not carried in the snapshot)")
    print("=" * 78)

    for record_type, table in load_tables(build_catalog()).items():
        if table.current_snapshot() is None:
            print(f"\n{record_type}: no snapshot, table is empty")
            continue

        rows = table.inspect.partitions().to_pylist()
        days = sorted(
            row["partition"][PARTITION_FIELD_NAME]
            for row in rows
            if row["partition"][PARTITION_FIELD_NAME] is not None
        )
        gross = sum(row["record_count"] for row in rows)
        deleted = sum(row["position_delete_record_count"] for row in rows)
        size_gib = sum(row["total_data_file_size_in_bytes"] for row in rows) / 1024**3
        files = sum(row["file_count"] for row in rows)
        span = (days[-1] - days[0]).days + 1 if days else 0
        held = set(days)
        missing = [
            str(days[0] + timedelta(days=offset))
            for offset in range(span)
            if days[0] + timedelta(days=offset) not in held
        ]

        print(f"\n{record_type}")
        print(f"  partitions   : {len(rows)} over a {span} day span")
        print(f"  rows         : {gross:,} gross - {deleted:,} deleted = {gross - deleted:,} net")
        print(f"  data files   : {files:,} ({size_gib:.2f} GiB)")
        print(f"  missing days : {missing or 'none'}")
        print("  thinnest days:")
        for row in sorted(rows, key=lambda r: r["record_count"])[:5]:
            print(f"      {row['partition'][PARTITION_FIELD_NAME]}  {row['record_count']:,} rows")


def main() -> None:
    started = time.monotonic()
    snapshot = build_snapshot()
    print(f"build_snapshot: {time.monotonic() - started:.1f}s", flush=True)

    print_snapshot(snapshot)
    print_partition_detail()


if __name__ == "__main__":
    main()
