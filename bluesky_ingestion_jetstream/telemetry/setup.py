"""Install the OTLP metric and log pipelines."""

import logging
import os

from opentelemetry import metrics
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.attributes.service_attributes import SERVICE_NAME as SERVICE_NAME_KEY

from bluesky_ingestion_jetstream.telemetry.constants import (
    ENDPOINT_VARIABLE,
    METRIC_EXPORT_INTERVAL_MILLIS,
    SERVICE_NAME,
)

logger = logging.getLogger(__name__)

# Held so `force_telemetry_flush` can reach them; the SDK exposes no global getter that
# returns the concrete providers.
_meter_provider: MeterProvider | None = None
_logger_provider: LoggerProvider | None = None


def is_configured() -> bool:
    """Whether an OTLP endpoint is set."""

    return bool(os.getenv(ENDPOINT_VARIABLE))


def build_resource() -> Resource:
    """Identity shared by both signals."""

    return Resource.create({SERVICE_NAME_KEY: SERVICE_NAME})


def build_meter_provider(resource: Resource) -> MeterProvider:
    """Metrics, pushed on a timer by the reader's own thread.

    Importing the http exporter pins the protocol, which Grafana Cloud requires
    and OTEL_EXPORTER_OTLP_PROTOCOL would otherwise have to carry.
    """

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(), export_interval_millis=METRIC_EXPORT_INTERVAL_MILLIS
    )
    return MeterProvider(resource=resource, metric_readers=[reader])


def build_logger_provider(resource: Resource) -> LoggerProvider:
    """Logs, so the per-flush lines are queryable next to the metrics."""

    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    return provider


def setup_telemetry() -> bool:
    """Wire up both pipelines, or do nothing when no endpoint is configured."""

    global _meter_provider, _logger_provider

    if not is_configured():
        logger.info("%s unset; running without telemetry", ENDPOINT_VARIABLE)
        return False

    resource = build_resource()

    _meter_provider = build_meter_provider(resource)
    metrics.set_meter_provider(_meter_provider)

    _logger_provider = build_logger_provider(resource)
    set_logger_provider(_logger_provider)
    logging.getLogger().addHandler(LoggingHandler(logger_provider=_logger_provider))

    logger.info("telemetry enabled as %s", SERVICE_NAME)
    return True


def force_telemetry_flush() -> None:
    """Export what is buffered, so a process about to die still reports."""

    for provider in (_meter_provider, _logger_provider):
        if provider is not None:
            provider.force_flush()
