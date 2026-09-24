"""Counters, recorded when something happens."""

import json
import logging

from opentelemetry import metrics

from bluesky_backfill_app.fetch_repos.storage.buffer import FlushSummary
from bluesky_backfill_app.telemetry.constants import (
    BYTES_PER_MEGABYTE,
    FLUSH_STATUS_OK,
    METER_NAME,
)
from bluesky_ingestion_jetstream.constants import RECORD_TYPES

logger = logging.getLogger(__name__)

RECORD_TYPE = "record_type"
REASON = "reason"
DID_STATUS = "did_status"

meter = metrics.get_meter(METER_NAME)

rows_written = meter.create_counter(
    "bluesky_backfill.rows.written",
    unit="{row}",
    description="Rows landed in S3, by record type.",
)
bytes_written = meter.create_counter(
    "bluesky_backfill.bytes.written",
    unit="By",
    description="Serialized JSON bytes landed, by record type. A proxy for volume.",
)
repos_landed = meter.create_counter(
    "bluesky_backfill.repos.landed",
    unit="{repo}",
    description="Repos landed in S3 and marked done.",
)
flush_failures = meter.create_counter(
    "bluesky_backfill.flush.failures",
    unit="{flush}",
    description="Flushes that raised; their repos are left to redeliver.",
)
repos_failed = meter.create_counter(
    "bluesky_backfill.repos.failed",
    unit="{repo}",
    description="Repo failures, by reason and the DID's status after.",
)


def record_flush(summary: FlushSummary, status: str) -> None:
    """Log one line per flush; count rows only if it landed."""

    if status == FLUSH_STATUS_OK:
        for record_type, rows in summary.rows.items():
            attributes = {RECORD_TYPE: record_type}
            rows_written.add(rows, attributes)
            bytes_written.add(summary.sizes[record_type], attributes)
        repos_landed.add(summary.repos)
    else:
        flush_failures.add(1)

    logger.info(json.dumps(get_flush_payload(summary, status)))


def record_repo_failure(reason: str, did_status: str) -> None:
    repos_failed.add(1, {REASON: reason, DID_STATUS: did_status})


def megabytes(byte_count: int) -> float:
    return round(byte_count / BYTES_PER_MEGABYTE, 2)


def get_flush_payload(summary: FlushSummary, status: str) -> dict[str, str | int | float]:
    """Flat, with every record type present, so LogQL's `| json` gives stable columns."""

    payload: dict[str, str | int | float] = {
        "event": "flush",
        "reason": summary.reason,
        "status": status,
        "repos": summary.repos,
    }
    for record_type in RECORD_TYPES:
        payload[f"{record_type}_rows"] = summary.rows.get(record_type, 0)
        payload[f"{record_type}_mb"] = megabytes(summary.sizes.get(record_type, 0))

    payload["total_rows"] = sum(summary.rows.values())
    payload["total_mb"] = megabytes(sum(summary.sizes.values()))
    return payload
