SERVICE_NAME = "bluesky-backfill-fetch-repos"

METER_NAME = "bluesky_backfill_app"

METRIC_EXPORT_INTERVAL_MILLIS = 60_000

OTLP_BASE = "https://otlp-gateway-prod-us-east-3.grafana.net/otlp"
METRICS_ENDPOINT = f"{OTLP_BASE}/v1/metrics"
LOGS_ENDPOINT = f"{OTLP_BASE}/v1/logs"

# Grafana Cloud token.
AUTH_TOKEN_VARIABLE = "OTEL_EXPORTER_OTLP_HEADERS"

QUEUE_MAIN = "main"
QUEUE_DLQ = "dlq"

FLUSH_STATUS_OK = "ok"
FLUSH_STATUS_FAILED = "failed"

# SI, matching Grafana's byte units.
BYTES_PER_MEGABYTE = 1_000_000
