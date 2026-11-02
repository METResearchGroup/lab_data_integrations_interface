"""Centralized environment variable loading.

Mapped names are loaded from AWS Secrets Manager in us-east-2. A non-empty
value in ``.env`` or the process environment overrides that secret.
``get_env_var`` writes a resolved secret back into ``os.environ`` under the
public name, so an SDK that reads ``OPENAI_API_KEY`` sees it after the check.

Public API: EnvVarsContainer.get_env_var(name, required=False)
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Final, NamedTuple

from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

from lib.aws.clients import build_client
from lib.aws.constants import AWS_REGION


class SecretRef(NamedTuple):
    """Where one public environment variable lives in Secrets Manager."""

    secret_id: str
    key: str | None = None


# Public name -> secret id and JSON key. ``key is None`` means the secret
# string itself is the value (not a JSON object).
# JEV_API_KEY reads the TYPESAFE_API_KEY field of jev-typesafe-api-key.
ENV_VAR_SOURCES: Final[dict[str, SecretRef]] = {
    "OPENAI_API_KEY": SecretRef("openai-api-key", "OPENAI_API_KEY"),
    "JEV_API_KEY": SecretRef("jev-typesafe-api-key", "TYPESAFE_API_KEY"),
}


class EnvVarsContainer:
    """Thread-safe singleton container for environment variables."""

    _instance: EnvVarsContainer | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._env_vars: dict[str, str | None] = {}
        self._secret_payloads: dict[str, dict[str, Any] | str] = {}
        self._client: Any = None
        self._dotenv_loaded = False
        self._init_lock = threading.Lock()

    @classmethod
    def get_env_var(cls, name: str, required: bool = False) -> str:
        """Get an environment variable after resolving Secrets Manager.

        Args:
            name: Environment variable name.
            required: If True, raises ValueError when missing or empty.

        Returns:
            The resolved string, or "" when the name is missing and not required.
        """
        instance: EnvVarsContainer = cls._get_instance()
        try:
            raw: str | None = instance._resolve(name)
        except ValueError:
            if required:
                raise
            return ""

        if required and raw is None:
            raise ValueError(
                f"{name} is required but is missing. Please set the {name} environment variable."
            )
        if required and isinstance(raw, str) and not raw.strip():
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
        return cls._instance

    def _resolve(self, name: str) -> str | None:
        cached = self._env_vars.get(name, _MISSING)
        if not isinstance(cached, _Missing):
            return cached
        with self._init_lock:
            cached = self._env_vars.get(name, _MISSING)
            if not isinstance(cached, _Missing):
                return cached
            return self._load_name(name)

    def _load_name(self, name: str) -> str | None:
        """Load the secret, then let a non-empty environment value replace it."""

        self._ensure_dotenv()
        env_value = os.getenv(name)
        if env_value is not None:
            env_value = env_value.strip() or None
        source = ENV_VAR_SOURCES.get(name)
        secret_value: str | None = None
        if source is not None:
            try:
                secret_value = self._value_from_secret(source)
            except ValueError:
                if env_value is None:
                    raise
            except BotoCoreError as exc:
                if env_value is None:
                    raise ValueError(
                        "Failed to load secret "
                        f"{source.secret_id} from AWS Secrets Manager ({type(exc).__name__})."
                    ) from exc
        if env_value is not None:
            self._env_vars[name] = env_value
            return env_value
        self._env_vars[name] = secret_value
        if secret_value:
            os.environ[name] = secret_value
        return secret_value

    def _ensure_dotenv(self) -> None:
        if self._dotenv_loaded:
            return
        env_path = (Path(__file__).resolve().parent / ".." / ".env").resolve()
        load_dotenv(env_path)
        self._dotenv_loaded = True

    def _secrets_client(self) -> Any:
        if self._client is None:
            self._client = build_client("secretsmanager", AWS_REGION, None)
        return self._client

    def _load_secret(self, secret_id: str) -> dict[str, Any] | str:
        cached = self._secret_payloads.get(secret_id)
        if cached is not None:
            return cached
        try:
            response = self._secrets_client().get_secret_value(SecretId=secret_id)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "Unknown")
            raise ValueError(
                f"Failed to load secret {secret_id} from AWS Secrets Manager ({code})."
            ) from exc
        secret_string = response.get("SecretString")
        if not isinstance(secret_string, str) or not secret_string.strip():
            raise ValueError(f"Secret {secret_id} has no SecretString.")
        stripped = secret_string.strip()
        if stripped.startswith("{"):
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Secret {secret_id} is not valid JSON.") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Secret {secret_id} JSON must be an object.")
            self._secret_payloads[secret_id] = payload
            return payload
        self._secret_payloads[secret_id] = stripped
        return stripped

    def _value_from_secret(self, source: SecretRef) -> str:
        payload = self._load_secret(source.secret_id)
        if source.key is None:
            if not isinstance(payload, str):
                raise ValueError(f"Secret {source.secret_id} is a JSON object, so it needs a key.")
            return payload
        if not isinstance(payload, dict):
            raise ValueError(
                f"Secret {source.secret_id} is a plain string and has no key {source.key}."
            )
        value = payload.get(source.key)
        if value is None or not str(value).strip():
            raise ValueError(f"Secret {source.secret_id} has no non-empty key {source.key}.")
        return str(value).strip()


class _Missing:
    """Sentinel for a name that has not been resolved yet."""


_MISSING = _Missing()
