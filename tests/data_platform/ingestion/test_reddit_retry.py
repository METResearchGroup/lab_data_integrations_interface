from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import prawcore.exceptions

from data_platform.ingestion import reddit_retry


def _mock_response(*, status_code: int = 429) -> MagicMock:
    return MagicMock(status_code=status_code, headers=SimpleNamespace(get=lambda *_: None))


def test_retry_reddit_request_retries_transient_errors() -> None:
    attempts = {"count": 0}

    @reddit_retry.retry_reddit_request(max_attempts=3, initial_delay=0.01, max_delay=0.02)
    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise prawcore.exceptions.TooManyRequests(_mock_response())
        return "ok"

    assert flaky() == "ok"
    assert attempts["count"] == 3


def test_retry_reddit_request_reraises_after_max_attempts() -> None:
    @reddit_retry.retry_reddit_request(max_attempts=2, initial_delay=0.01, max_delay=0.02)
    def always_fails() -> None:
        raise prawcore.exceptions.ServerError(_mock_response(status_code=503))

    with pytest.raises(prawcore.exceptions.ServerError):
        always_fails()
