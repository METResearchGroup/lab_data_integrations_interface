"""The /query route acks immediately and hands the work to a background task."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.auth import current_user_email
from backend.main import app

EMAIL = "someone@example.invalid"
QUERY = "posts in July"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "backend.routes.query.handle_query", lambda query, email: calls.append((query, email))
    )

    app.dependency_overrides[current_user_email] = lambda: EMAIL
    with TestClient(app) as test_client:
        yield test_client, calls
    app.dependency_overrides.clear()


def test_query_is_acked_and_handed_off(client) -> None:
    test_client, calls = client
    response = test_client.post("/query", json=QUERY)

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert calls == [(QUERY, EMAIL)]


def test_query_without_a_token_is_rejected() -> None:
    """The auth dependency must not be reachable without credentials."""

    with TestClient(app) as test_client:
        assert test_client.post("/query", json=QUERY).status_code == 401
