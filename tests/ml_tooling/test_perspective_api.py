from __future__ import annotations

from typing import Any

import pytest

from ml_tooling import perspective_api


def _response_body(
    toxicity: float,
    severe_toxicity: float,
) -> dict[str, Any]:
    return {
        "attributeScores": {
            "TOXICITY": {"summaryScore": {"value": toxicity}},
            "SEVERE_TOXICITY": {"summaryScore": {"value": severe_toxicity}},
        }
    }


def test_parse_perspective_response_returns_both_probs() -> None:
    toxicity, severe = perspective_api._parse_perspective_response(
        _response_body(0.42, 0.17)
    )
    assert toxicity == 0.42
    assert severe == 0.17


def test_parse_perspective_response_missing_key_raises() -> None:
    with pytest.raises(RuntimeError, match="Unexpected Perspective API response shape"):
        perspective_api._parse_perspective_response({"attributeScores": {}})


def test_get_toxicity_probs_parses_http_response(monkeypatch) -> None:
    monkeypatch.setattr(
        perspective_api.EnvVarsContainer,
        "get_env_var",
        lambda name, required=True: "test-key",
    )
    monkeypatch.setattr(
        perspective_api,
        "_post_analyze",
        lambda payload: _response_body(0.6, 0.8),
    )

    toxicity, severe = perspective_api.get_toxicity_probs("some text")

    assert toxicity == 0.6
    assert severe == 0.8


def test_get_toxicity_prob_returns_first_score(monkeypatch) -> None:
    monkeypatch.setattr(
        perspective_api,
        "get_toxicity_probs",
        lambda text: (0.25, 0.9),
    )

    assert perspective_api.get_toxicity_prob("some text") == 0.25
