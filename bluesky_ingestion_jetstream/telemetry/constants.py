"""Telemetry configuration."""

# Identity, set here rather than read from OTEL_SERVICE_NAME: the shared root
# .env names the backend, and a Resource attribute set in code overrides it.
SERVICE_NAME = "bluesky-ingestion-jetstream"

METER_NAME = "bluesky_ingestion_jetstream"

# Metrics are pushed on this interval, not when a value changes.
METRIC_EXPORT_INTERVAL_MILLIS = 60_000

# Grafana Cloud's OTLP gateway for this stack.
OTLP_BASE = "https://otlp-gateway-prod-us-east-3.grafana.net/otlp"

METRICS_ENDPOINT = f"{OTLP_BASE}/v1/metrics"
LOGS_ENDPOINT = f"{OTLP_BASE}/v1/logs"

# Env var holding the Grafana Cloud token
AUTH_TOKEN_VARIABLE = "OTEL_EXPORTER_OTLP_HEADERS"
