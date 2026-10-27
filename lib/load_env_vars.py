"""Centralized environment variable loading.

This module exists to avoid import-time side effects spread across the codebase.
It loads two sources, in this order:
- AWS Secrets Manager, for the names in _SECRET_SOURCES
- .env and the process environment, which override a secret when the name is set

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

# name -> (Secrets Manager id, JSON fields tried in order when the secret is an object)
_SECRET_SOURCES: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "OPENAI_API_KEY": (
        "openai-api-key",
        ("OPENAI_API_KEY", "openai_api_key", "api_key", "key"),
    ),
}

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
        self._load_errors: dict[str, str] = {}
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

        if required and _missing(raw):
            detail = instance._load_errors.get(name)
            if detail:
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
        """Load Secrets Manager first. A set environment value then overrides it."""

        for name, (secret_id, fields) in _SECRET_SOURCES.items():
            try:
                self._env_vars[name] = _fetch_named_key(
                    secret_id=secret_id,
                    label=name,
                    fields=fields,
                )
            except ValueError as exc:
                self._env_vars[name] = None
                self._load_errors[name] = str(exc)

        env_path: Path = (Path(__file__).resolve().parent / ".." / ".env").resolve()
        load_dotenv(env_path)
        for key in self._env_var_types:
            env_value = os.getenv(key)
            if env_value is not None and env_value.strip():
                self._env_vars[key] = env_value.strip()
                self._load_errors.pop(key, None)
            elif key not in self._env_vars:
                self._env_vars[key] = None


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
