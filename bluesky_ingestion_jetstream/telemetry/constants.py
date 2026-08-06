"""Telemetry configuration."""

# Identity, set here rather than read from OTEL_SERVICE_NAME: the shared root
# .env names the backend, and a Resource attribute set in code overrides it.
SERVICE_NAME = "bluesky-ingestion-jetstream"

METER_NAME = "bluesky_ingestion_jetstream"

# Metrics are pushed on this interval, not when a value changes.
METRIC_EXPORT_INTERVAL_MILLIS = 60_000

# Everything else (headers, endpoint) comes from the environment. Unset means
# telemetry is skipped, so local runs and tests do not export anywhere.
ENDPOINT_VARIABLE = "OTEL_EXPORTER_OTLP_ENDPOINT"
