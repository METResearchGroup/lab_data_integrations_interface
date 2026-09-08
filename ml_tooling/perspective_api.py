"""Google Perspective API client for toxicity scoring.

Run from the repo root:

    PYTHONPATH=. uv run python ml_tooling/perspective_api.py
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from lib.load_env_vars import EnvVarsContainer

PERSPECTIVE_API_URL = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
TOXICITY_ATTRIBUTE = "TOXICITY"
SEVERE_TOXICITY_ATTRIBUTE = "SEVERE_TOXICITY"


def _parse_perspective_response(body: dict[str, Any]) -> tuple[float, float]:
    try:
        toxicity_prob = float(
            body["attributeScores"][TOXICITY_ATTRIBUTE]["summaryScore"]["value"]
        )
        severe_toxicity_prob = float(
            body["attributeScores"][SEVERE_TOXICITY_ATTRIBUTE]["summaryScore"]["value"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Unexpected Perspective API response shape: {body}") from exc
    return toxicity_prob, severe_toxicity_prob


def _post_analyze(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = EnvVarsContainer.get_env_var("GOOGLE_API_KEY", required=True)
    url = f"{PERSPECTIVE_API_URL}?key={api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Perspective API request failed with status {exc.code}: {error_body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Perspective API request failed: {exc.reason}") from exc


def get_toxicity_probs(text: str) -> tuple[float, float]:
    """Return TOXICITY and SEVERE_TOXICITY probabilities from one API call."""
    payload = {
        "comment": {"text": text},
        "languages": ["en"],
        "requestedAttributes": {
            TOXICITY_ATTRIBUTE: {},
            SEVERE_TOXICITY_ATTRIBUTE: {},
        },
    }
    body = _post_analyze(payload)
    return _parse_perspective_response(body)


def get_toxicity_prob(text: str) -> float:
    """Return the Perspective API toxicity probability for a single text string."""
    return get_toxicity_probs(text)[0]


if __name__ == "__main__":
    samples = [
        "Thanks for sharing this thoughtful update.",
        "You are an idiot and nobody likes you.",
    ]
    for text in samples:
        toxicity_prob, severe_toxicity_prob = get_toxicity_probs(text)
        print(f"{toxicity_prob:.4f} {severe_toxicity_prob:.4f}  {text!r}")
