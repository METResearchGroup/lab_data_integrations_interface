"""OpenTelemetry wiring for the Jetstream ingester."""

from bluesky_ingestion_jetstream.telemetry.instruments import (
    record_dead_letter,
    record_dropped,
    record_flush,
    record_reconnect,
)
from bluesky_ingestion_jetstream.telemetry.setup import force_telemetry_flush, setup_telemetry

__all__ = [
    "force_telemetry_flush",
    "record_dead_letter",
    "record_dropped",
    "record_flush",
    "record_reconnect",
    "setup_telemetry",
]
