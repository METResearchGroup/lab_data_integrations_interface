from __future__ import annotations

import pytest
from atproto_client.exceptions import RequestException, UnauthorizedError
from atproto_client.request import Response

from data_platform.ingestion.bluesky_retry import _is_retryable_bluesky_error, retry_bluesky_request


def test_is_retryable_on_429_request_exception() -> None:
    response = Response(success=False, status_code=429, content=None, headers={})
    assert _is_retryable_bluesky_error(RequestException(response)) is True


def test_is_not_retryable_on_401() -> None:
    response = Response(success=False, status_code=401, content=None, headers={})
    assert _is_retryable_bluesky_error(UnauthorizedError(response)) is False


def test_retry_bluesky_request_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"count": 0}

    @retry_bluesky_request(max_attempts=4, initial_delay=0.01, max_delay=0.02)
    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            response = Response(success=False, status_code=429, content=None, headers={})
            raise RequestException(response)
        return "ok"

    monkeypatch.setattr(
        "data_platform.ingestion.bluesky_retry.wait_exponential_jitter",
        lambda **kwargs: lambda retry_state: 0,
    )
    assert flaky() == "ok"
    assert attempts["count"] == 3


def test_retry_bluesky_request_does_not_retry_401(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"count": 0}

    @retry_bluesky_request(max_attempts=4, initial_delay=0.01, max_delay=0.02)
    def unauthorized() -> str:
        attempts["count"] += 1
        response = Response(success=False, status_code=401, content=None, headers={})
        raise UnauthorizedError(response)

    monkeypatch.setattr(
        "data_platform.ingestion.bluesky_retry.wait_exponential_jitter",
        lambda **kwargs: lambda retry_state: 0,
    )
    with pytest.raises(UnauthorizedError):
        unauthorized()
    assert attempts["count"] == 1
