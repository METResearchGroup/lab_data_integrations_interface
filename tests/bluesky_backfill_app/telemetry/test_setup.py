from bluesky_backfill_app.telemetry.constants import AUTH_TOKEN_VARIABLE, SERVICE_NAME
from bluesky_backfill_app.telemetry.setup import build_resource, is_configured, setup_telemetry


def test_service_name_beats_the_environment(monkeypatch):
    """The root .env names the backend."""

    monkeypatch.setenv("OTEL_SERVICE_NAME", "backend")

    assert build_resource().attributes["service.name"] == SERVICE_NAME


def test_each_process_gets_an_instance_id():
    """Keeps workers' counters on separate series."""

    assert build_resource().attributes["service.instance.id"]


def test_unconfigured_without_a_token(monkeypatch):
    monkeypatch.delenv(AUTH_TOKEN_VARIABLE, raising=False)

    assert is_configured() is False
    assert setup_telemetry() is False


def test_configured_with_a_token(monkeypatch):
    monkeypatch.setenv(AUTH_TOKEN_VARIABLE, "Authorization=Basic%20abc123")

    assert is_configured() is True
