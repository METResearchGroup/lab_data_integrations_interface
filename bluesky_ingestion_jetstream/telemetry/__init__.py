"""OpenTelemetry wiring for the Jetstream ingester."""

from bluesky_ingestion_jetstream.telemetry.gauges import register_cursor_tracker
from bluesky_ingestion_jetstream.telemetry.instruments import (
    record_connection_failure,
    record_dead_letter,
    record_dropped,
    record_flush,
)
from bluesky_ingestion_jetstream.telemetry.setup import force_telemetry_flush, setup_telemetry

__all__ = [
    "force_telemetry_flush",
    "record_dead_letter",
    "record_dropped",
    "record_flush",
    "record_connection_failure",
    "register_cursor_tracker",
    "setup_telemetry",
]
