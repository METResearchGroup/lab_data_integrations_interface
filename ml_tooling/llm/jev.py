"""Ask TypeSafe Jev a choice question.

The client posts to https://api.typesafe.ai/v1/systemone with model jev-latest.
The key comes from EnvVarsContainer, name JEV_API_KEY.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

from lib.load_env_vars import EnvVarsContainer

_JEV_URL = "https://api.typesafe.ai/v1/systemone"
_JEV_MODEL = "jev-latest"
_JEV_ATTEMPTS = 3
_RETRY_STATUS = frozenset({429, 529})

_status = "not_called"
_status_lock = threading.Lock()


def last_status() -> str:
    """A short status from the last call, with no response body."""

    with _status_lock:
        return _status


def ask_choice(
    state: str,
    *,
    question_id: str,
    instructions: str,
    criteria: dict[str, str],
    allowed: tuple[str, ...] | None = None,
) -> str | None:
    """Return one choice label, or None when Jev does not answer.

    Parameters
    ----------
    state : str
        The text Jev classifies.
    question_id : str
        The key under ``questions`` and under ``answers``.
    instructions : str
        How to choose among the criteria.
    criteria : dict[str, str]
        Label to the sentence that defines that label.
    allowed : tuple[str, ...] | None
        When set, a label outside this tuple is treated as no answer.

    Returns
    -------
    str | None
        The label, or None. ``last_status`` is ``ok``, ``no_key``,
        ``no_choice``, ``unreachable``, or ``http_<code>``.
    """

    key = EnvVarsContainer.get_env_var("JEV_API_KEY", required=False)
    if not key:
        _set_status("no_key")
        return None
    payload = {
        "model": _JEV_MODEL,
        "state": state,
        "questions": {
            question_id: {
                "type": "choice",
                "instructions": instructions,
                "criteria": criteria,
            }
        },
    }
    request = urllib.request.Request(
        _JEV_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "lab-data-integrations-interface",
        },
        method="POST",
    )
    body = _post(request)
    if body is None:
        return None
    choice = _choice_from_body(body, question_id)
    if choice is None or (allowed is not None and choice not in allowed):
        _set_status("no_choice")
        return None
    _set_status("ok")
    return choice


def _set_status(status: str) -> None:
    global _status
    with _status_lock:
        _status = status


def _choice_from_body(body: dict, question_id: str) -> str | None:
    answers = body.get("answers")
    if not isinstance(answers, dict):
        return None
    question = answers.get(question_id)
    if not isinstance(question, dict):
        return None
    choice = question.get("choice")
    if isinstance(choice, str) and choice.strip():
        return choice
    return None


def _post(request: urllib.request.Request) -> dict | None:
    """POST one request. Retries 429 and 529. Returns None on failure."""

    delay = 1.0
    for attempt in range(_JEV_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
                body = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            exc.close()
            if exc.code in _RETRY_STATUS and attempt + 1 < _JEV_ATTEMPTS:
                time.sleep(delay)
                delay *= 2
                continue
            _set_status(f"http_{exc.code}")
            return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            _set_status("unreachable")
            return None
        if isinstance(body, dict):
            return body
        _set_status("unreachable")
        return None
    _set_status("unreachable")
    return None
