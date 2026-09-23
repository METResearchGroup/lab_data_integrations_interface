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

from bluesky_backfill_app.telemetry.constants import (
    AUTH_TOKEN_VARIABLE,
    LOGS_ENDPOINT,
    METRIC_EXPORT_INTERVAL_MILLIS,
    METRICS_ENDPOINT,
    SERVICE_NAME,
)

logger = logging.getLogger(__name__)

_meter_provider: MeterProvider | None = None
_logger_provider: LoggerProvider | None = None


def is_configured() -> bool:
    return bool(os.getenv(AUTH_TOKEN_VARIABLE))


def build_resource() -> Resource:
    """
    The SDK adds a random `service.instance.id`, so workers get separate series.
    """

    return Resource.create({SERVICE_NAME_KEY: SERVICE_NAME})


def setup_telemetry() -> bool:
    """Wire up metrics and logs, or do nothing without a token."""

    global _meter_provider, _logger_provider

    if not is_configured():
        logger.info("%s unset; running without telemetry", AUTH_TOKEN_VARIABLE)
        return False

    resource = build_resource()

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=METRICS_ENDPOINT),
        export_interval_millis=METRIC_EXPORT_INTERVAL_MILLIS,
    )
    _meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(_meter_provider)

    _logger_provider = LoggerProvider(resource=resource)
    _logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=LOGS_ENDPOINT))
    )
    set_logger_provider(_logger_provider)
    logging.getLogger().addHandler(LoggingHandler(logger_provider=_logger_provider))

    logger.info("telemetry enabled as %s", SERVICE_NAME)
    return True


def force_telemetry_flush() -> None:
    for provider in (_meter_provider, _logger_provider):
        if provider is not None:
            provider.force_flush()
