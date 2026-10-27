"""Centralized environment variable loading.

This module exists to avoid import-time side effects spread across the codebase.
It encapsulates:
- Loading .env from repo root via python-dotenv
- OPENAI_API_KEY from AWS Secrets Manager id openai-api-key in us-east-2
- Type-safe retrieval with optional required-flag

Public API: EnvVarsContainer.get_env_var(name, required=False)
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Final

from dotenv import load_dotenv

from lib.aws.clients import build_client
from lib.aws.constants import AWS_REGION

_OPENAI_API_KEY = "OPENAI_API_KEY"
_OPENAI_SECRET_ID = "openai-api-key"
_OPENAI_JSON_FIELDS = ("OPENAI_API_KEY", "openai_api_key", "api_key", "key")

ENV_VAR_TYPES: Final[dict[str, type[str]]] = {
    "OPENAI_API_KEY": str,
    "WANDB_API_KEY": str,
    "REDDIT_CLIENT_ID": str,
    "REDDIT_SECRET": str,
    "REDDIT_REDIRECT_URI": str,
    "REDDIT_USERNAME": str,
    "REDDIT_PASSWORD": str,
    "BLUESKY_HANDLE": str,
    "BLUESKY_PASSWORD": str,
    "OPIK_WORKSPACE": str,
    "GOOGLE_API_KEY": str,
    "X_CONSUMER_KEY": str,
    "X_SECRET_KEY": str,
    "X_BEARER_TOKEN": str,
}


class EnvVarsContainer:
    """Thread-safe singleton container for environment variables."""

    _instance: EnvVarsContainer | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._initialized = False
        self._env_vars: dict[str, str | None] = {}
        self._env_var_types: dict[str, type[str]] = ENV_VAR_TYPES
        self._openai_load_error: str | None = None
        self._init_lock = threading.Lock()

    @classmethod
    def get_env_var(cls, name: str, required: bool = False) -> str:
        """Get an environment variable after container initialization.

        Args:
            name: Environment variable name.
            required: If True, raises ValueError when missing or empty.

        Returns:
            Value (cast per _env_var_types) or default ("" when missing).
        """
        instance: EnvVarsContainer = cls._get_instance()
        raw: str | None = instance._env_vars.get(name)

        if required and name == _OPENAI_API_KEY and _missing(raw):
            detail = instance._openai_load_error or (
                "OPENAI_API_KEY is required but is missing. "
                "Load it through EnvVarsContainer from id openai-api-key in us-east-2."
            )
            raise ValueError(detail)

        if required:
            if raw is None:
                raise ValueError(
                    f"{name} is required but is missing. "
                    f"Please set the {name} environment variable."
                )
            if isinstance(raw, str) and not raw.strip():
                raise ValueError(
                    f"{name} is required but is empty. "
                    f"Please set the {name} environment variable to a non-empty value."
                )

        if raw is None:
            return ""
        return str(raw)

    @classmethod
    def _get_instance(cls) -> EnvVarsContainer:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        cls._instance._ensure_initialized()
        return cls._instance

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            self._initialize_env_vars()
            self._initialized = True

    def _initialize_env_vars(self) -> None:
        env_path: Path = (Path(__file__).resolve().parent / ".." / ".env").resolve()
        load_dotenv(env_path)
        # This name is loaded from Secrets Manager below. Drop any copy .env
        # or the process environment left behind so callers cannot use it.
        os.environ.pop(_OPENAI_API_KEY, None)
        for key in self._env_var_types:
            if key == _OPENAI_API_KEY:
                continue
            self._env_vars[key] = os.getenv(key)
        self._load_openai_api_key()

    def _load_openai_api_key(self) -> None:
        """Read OPENAI_API_KEY from Secrets Manager. Leave it empty when that fails."""

        try:
            self._env_vars[_OPENAI_API_KEY] = _fetch_openai_api_key()
            self._openai_load_error = None
        except ValueError as exc:
            self._env_vars[_OPENAI_API_KEY] = None
            self._openai_load_error = str(exc)


def _missing(raw: str | None) -> bool:
    return raw is None or (isinstance(raw, str) and not raw.strip())


def _safe_field_name(field: object) -> str:
    text = str(field)
    if "sk-" in text.lower() or len(text) > 40:
        return "[redacted]"
    return text


def _key_from_text(text: str, *, label: str, secret_id: str, fields: tuple[str, ...]) -> str:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return stripped
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        raise ValueError(
            f"{label} could not be loaded from id {secret_id} in "
            f"{AWS_REGION}: the stored string starts with '{{' and is not JSON."
        ) from None
    if not isinstance(parsed, dict):
        raise ValueError(
            f"{label} could not be loaded from id {secret_id} in "
            f"{AWS_REGION}: the stored JSON value is not an object."
        )
    for field in fields:
        value = parsed.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    present = ", ".join(sorted(_safe_field_name(field) for field in parsed))
    raise ValueError(
        f"{label} could not be loaded from id {secret_id} in "
        f"{AWS_REGION}: the JSON object has none of the expected fields. "
        f"Fields present: {present}."
    )


def _error_code(exc: Exception) -> str:
    response: Any = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error")
        if isinstance(error, dict) and isinstance(error.get("Code"), str):
            return error["Code"]
    return type(exc).__name__


def _fetch_named_key(*, secret_id: str, label: str, fields: tuple[str, ...]) -> str:
    try:
        client = build_client("secretsmanager", AWS_REGION, None)
        payload = client.get_secret_value(SecretId=secret_id)
    except Exception as exc:
        raise ValueError(
            f"{label} could not be loaded from id {secret_id} in {AWS_REGION} ({_error_code(exc)})."
        ) from None

    raw = payload.get("SecretString") if isinstance(payload, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(
            f"{label} could not be loaded from id {secret_id} in "
            f"{AWS_REGION}: the stored string is empty."
        )
    return _key_from_text(raw, label=label, secret_id=secret_id, fields=fields)


def _fetch_openai_api_key() -> str:
    return _fetch_named_key(
        secret_id=_OPENAI_SECRET_ID,
        label=_OPENAI_API_KEY,
        fields=_OPENAI_JSON_FIELDS,
    )
