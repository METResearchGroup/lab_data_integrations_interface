"""The /query route acks immediately and hands the work to a background task."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.auth import current_user_email
from backend.main import app
from backend.rate_limit import QUERY_INTERVAL_SECONDS, QueryRateLimiter

EMAIL = "someone@example.invalid"
OTHER_EMAIL = "someone-else@example.invalid"
QUERY = "posts in July"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "backend.routes.query.handle_query", lambda query, email: calls.append((query, email))
    )

    now = [0.0]
    monkeypatch.setattr("backend.routes.query.limiter", QueryRateLimiter(clock=lambda: now[0]))

    app.dependency_overrides[current_user_email] = lambda: EMAIL
    with TestClient(app) as test_client:
        yield test_client, calls, now
    app.dependency_overrides.clear()


def test_query_is_acked_and_handed_off(client) -> None:
    test_client, calls, _ = client
    response = test_client.post("/query", json=QUERY)

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert calls == [(QUERY, EMAIL)]


def test_query_without_a_token_is_rejected() -> None:
    """The auth dependency must not be reachable without credentials."""

    with TestClient(app) as test_client:
        assert test_client.post("/query", json=QUERY).status_code == 401


def test_second_query_within_the_interval_is_rejected(client) -> None:
    test_client, calls, now = client
    test_client.post("/query", json=QUERY)
    now[0] += 20

    response = test_client.post("/query", json=QUERY)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == str(QUERY_INTERVAL_SECONDS - 20)
    assert (
        response.json()["detail"]
        == f"Too many queries. Try again in {QUERY_INTERVAL_SECONDS - 20}s."
    )
    assert calls == [(QUERY, EMAIL)]


def test_query_is_accepted_once_the_interval_passes(client) -> None:
    test_client, calls, now = client
    test_client.post("/query", json=QUERY)
    now[0] += QUERY_INTERVAL_SECONDS

    assert test_client.post("/query", json=QUERY).status_code == 202
    assert len(calls) == 2


def test_rejected_query_does_not_restart_the_interval(client) -> None:
    test_client, _, now = client
    test_client.post("/query", json=QUERY)
    now[0] += QUERY_INTERVAL_SECONDS - 1
    assert test_client.post("/query", json=QUERY).status_code == 429

    now[0] += 1
    assert test_client.post("/query", json=QUERY).status_code == 202


def test_users_are_limited_independently(client) -> None:
    test_client, calls, _ = client
    test_client.post("/query", json=QUERY)
    app.dependency_overrides[current_user_email] = lambda: OTHER_EMAIL

    assert test_client.post("/query", json=QUERY).status_code == 202
    assert calls == [(QUERY, EMAIL), (QUERY, OTHER_EMAIL)]


def test_malformed_body_does_not_spend_the_slot(client) -> None:
    test_client, calls, _ = client
    assert test_client.post("/query", json={"query": QUERY}).status_code == 422

    assert test_client.post("/query", json=QUERY).status_code == 202
    assert calls == [(QUERY, EMAIL)]
