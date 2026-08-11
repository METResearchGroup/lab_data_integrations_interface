"""OpenTelemetry wiring for the backend."""

from backend.telemetry.setup import force_telemetry_flush, setup_telemetry

__all__ = [
    "force_telemetry_flush",
    "setup_telemetry",
]
