"""Tests for the telemetry bootstrap."""

from bluesky_ingestion_jetstream.telemetry.constants import (
    AUTH_TOKEN_VARIABLE,
    LOGS_ENDPOINT,
    METRICS_ENDPOINT,
    SERVICE_NAME,
)
from bluesky_ingestion_jetstream.telemetry.setup import build_resource, is_configured


class TestBuildResource:
    def test_service_name_beats_the_environment(self, monkeypatch):
        """The shared root .env names the backend; inheriting it would merge the
        two services into one in Grafana, with nothing visibly wrong."""

        monkeypatch.setenv("OTEL_SERVICE_NAME", "backend")

        assert build_resource().attributes["service.name"] == SERVICE_NAME


class TestIsConfigured:
    def test_false_without_a_token(self, monkeypatch):
        """Unconfigured must mean silent, not exporting to localhost by default."""

        monkeypatch.delenv(AUTH_TOKEN_VARIABLE, raising=False)

        assert is_configured() is False

    def test_true_with_a_token(self, monkeypatch):
        monkeypatch.setenv(AUTH_TOKEN_VARIABLE, "Authorization=Basic%20abc123")

        assert is_configured() is True


class TestEndpoints:
    def test_carry_the_signal_path(self):
        """Passed as kwargs the SDK uses them verbatim, unlike the env var, from
        which it derives the per-signal path itself."""

        assert METRICS_ENDPOINT.endswith("/v1/metrics")
        assert LOGS_ENDPOINT.endswith("/v1/logs")
