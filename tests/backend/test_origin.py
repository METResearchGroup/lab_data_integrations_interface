"""Only requests carrying CloudFront's shared secret reach the routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.origin import HEADER, SECRET_VARIABLE

SECRET = "shared-secret"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(SECRET_VARIABLE, SECRET)
    with TestClient(app) as test_client:
        yield test_client


def test_request_without_the_secret_is_forbidden(client) -> None:
    assert client.post("/query", json="q").status_code == 403


def test_request_with_a_wrong_secret_is_forbidden(client) -> None:
    assert client.post("/query", json="q", headers={HEADER: "guess"}).status_code == 403


def test_request_with_the_secret_reaches_the_route(client) -> None:
    # No bearer token, so auth answers instead of the guard.
    assert client.post("/query", json="q", headers={HEADER: SECRET}).status_code == 401


def test_health_skips_the_guard(client) -> None:
    assert client.get("/health").status_code == 200


def test_guard_is_off_when_the_secret_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SECRET_VARIABLE, raising=False)
    with TestClient(app) as test_client:
        assert test_client.post("/query", json="q").status_code == 401
