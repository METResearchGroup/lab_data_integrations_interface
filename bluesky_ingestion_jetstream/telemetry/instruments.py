"""Counters, and the calls that record to them.

Instruments are built at import. Until `setup_telemetry` installs a provider the
meter is a proxy that discards what it is given, so importing this module never
requires telemetry to be configured.
"""

import json
import logging

from opentelemetry import metrics

from bluesky_ingestion_jetstream.storage.buffer import FlushSummary
from bluesky_ingestion_jetstream.telemetry.constants import METER_NAME

logger = logging.getLogger(__name__)

RECORD_TYPE = "record_type"
REASON = "reason"

meter = metrics.get_meter(METER_NAME)

rows_written = meter.create_counter(
    "bluesky_jetstream.rows.written",
    unit="{row}",
    description="Rows committed to Iceberg, by record type.",
)
bytes_written = meter.create_counter(
    "bluesky_jetstream.bytes.written",
    unit="By",
    description="Serialized JSON bytes committed, by record type. A proxy for volume.",
)
reconnects = meter.create_counter(
    "bluesky_jetstream.reconnects",
    unit="{disconnect}",
    description="Jetstream socket drops, by reason.",
)
dead_letters = meter.create_counter(
    "bluesky_jetstream.dead_letters",
    unit="{row}",
    description="Rows that missed Iceberg and landed in the dead letter instead.",
)
dropped = meter.create_counter(
    "bluesky_jetstream.dropped",
    unit="{row}",
    description="Rows lost outright: neither Iceberg nor the dead letter took them.",
)


def record_flush(summary: FlushSummary) -> None:
    """Count what a flush wrote, and log it as one line per flush.

    The counters and the log line come from the same summary, so the 24h totals
    and the per-flush table cannot disagree.
    """

    for record_type, rows in summary.rows.items():
        attributes = {RECORD_TYPE: record_type}
        rows_written.add(rows, attributes)
        bytes_written.add(summary.sizes[record_type], attributes)

    # Flat keys and a bare JSON object, so LogQL's `| json` gives one column per
    # field without further parsing.
    payload: dict[str, str | int] = {"event": "flush", REASON: summary.reason}
    for record_type, rows in summary.rows.items():
        payload[f"{record_type}_rows"] = rows
        payload[f"{record_type}_bytes"] = summary.sizes[record_type]

    logger.info(json.dumps(payload))


def record_reconnect(reason: str) -> None:
    """Count a socket drop under a bounded reason."""

    reconnects.add(1, {REASON: reason})


def record_dead_letter(record_type: str, rows: int) -> None:
    """Count rows that missed Iceberg but were persisted elsewhere."""

    dead_letters.add(rows, {RECORD_TYPE: record_type})


def record_dropped(record_type: str, rows: int) -> None:
    """Count rows nothing durable accepted."""

    dropped.add(rows, {RECORD_TYPE: record_type})
