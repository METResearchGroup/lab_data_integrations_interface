"""Install the OTLP trace and log pipelines."""

import logging
import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.semconv.attributes.service_attributes import SERVICE_NAME as SERVICE_NAME_KEY

from backend.telemetry.constants import (
    AUTH_TOKEN_VARIABLE,
    LOGS_ENDPOINT,
    SERVICE_NAME,
    TRACES_ENDPOINT,
)

logger = logging.getLogger(__name__)

# Held so `force_telemetry_flush` can reach them; the SDK exposes no global getter that
# returns the concrete providers.
_tracer_provider: TracerProvider | None = None
_logger_provider: LoggerProvider | None = None


def is_configured() -> bool:
    """Whether the Grafana Cloud token is set."""

    return bool(os.getenv(AUTH_TOKEN_VARIABLE))


def build_resource() -> Resource:
    """Identity shared by both signals."""

    return Resource.create({SERVICE_NAME_KEY: SERVICE_NAME})


def build_tracer_provider(resource: Resource) -> TracerProvider:
    """Traces, batched off the request path by the processor's own thread.

    Importing the http exporter pins the protocol, which Grafana Cloud requires
    and OTEL_EXPORTER_OTLP_PROTOCOL would otherwise have to carry.
    """

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=TRACES_ENDPOINT)))
    return provider


def build_logger_provider(resource: Resource) -> LoggerProvider:
    """Logs, so request lines are queryable next to the spans."""

    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=LOGS_ENDPOINT))
    )
    return provider


def setup_telemetry(app: FastAPI) -> bool:
    """Wire up both pipelines, or do nothing when no token is configured."""

    global _tracer_provider, _logger_provider

    if not is_configured():
        logger.info("%s unset; running without telemetry", AUTH_TOKEN_VARIABLE)
        return False

    resource = build_resource()

    _tracer_provider = build_tracer_provider(resource)
    trace.set_tracer_provider(_tracer_provider)

    _logger_provider = build_logger_provider(resource)
    set_logger_provider(_logger_provider)
    logging.getLogger().addHandler(LoggingHandler(logger_provider=_logger_provider))

    # Supplies the per-request spans; without it the provider exports nothing.
    FastAPIInstrumentor.instrument_app(app, tracer_provider=_tracer_provider)

    logger.info("telemetry enabled as %s", SERVICE_NAME)
    return True


def force_telemetry_flush() -> None:
    """Export what is buffered, so a process about to die still reports."""

    for provider in (_tracer_provider, _logger_provider):
        if provider is not None:
            provider.force_flush()
