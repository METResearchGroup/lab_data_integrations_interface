"""Tests for the telemetry bootstrap."""

from bluesky_ingestion_jetstream.telemetry.constants import ENDPOINT_VARIABLE, SERVICE_NAME
from bluesky_ingestion_jetstream.telemetry.setup import build_resource, is_configured


class TestBuildResource:
    def test_service_name_beats_the_environment(self, monkeypatch):
        """The shared root .env names the backend; inheriting it would merge the
        two services into one in Grafana, with nothing visibly wrong."""

        monkeypatch.setenv("OTEL_SERVICE_NAME", "backend")

        assert build_resource().attributes["service.name"] == SERVICE_NAME


class TestIsConfigured:
    def test_false_without_an_endpoint(self, monkeypatch):
        """Unconfigured must mean silent, not exporting to localhost by default."""

        monkeypatch.delenv(ENDPOINT_VARIABLE, raising=False)

        assert is_configured() is False

    def test_true_with_an_endpoint(self, monkeypatch):
        monkeypatch.setenv(ENDPOINT_VARIABLE, "https://otlp-gateway-x.grafana.net/otlp")

        assert is_configured() is True
