"""Telemetry configuration."""

SERVICE_NAME = "backend"

# Grafana Cloud's OTLP gateway for this stack.
OTLP_BASE = "https://otlp-gateway-prod-us-east-3.grafana.net/otlp"

TRACES_ENDPOINT = f"{OTLP_BASE}/v1/traces"
LOGS_ENDPOINT = f"{OTLP_BASE}/v1/logs"

# Env var holding the Grafana Cloud token
AUTH_TOKEN_VARIABLE = "OTEL_EXPORTER_OTLP_HEADERS"
