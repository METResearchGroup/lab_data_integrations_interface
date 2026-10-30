"""Fill unset environment variables from AWS Secrets Manager.

Cloudflare containers receive AWS credentials and read application secrets
themselves. A variable that is already present is left alone, including an
empty value, so a local `.env` wins. This module never prints secret values.

Call `fill_unset_secrets` after `load_dotenv` and before any code that reads
the variables. Pass `only` to load a subset, which is what Jetstream and the
backfill worker do for the telemetry header.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.parse import urlparse

from botocore.exceptions import ClientError

from lib.aws.clients import build_client
from lib.aws.constants import AWS_REGION
from lib.aws.error_codes import error_code

logger = logging.getLogger(__name__)

# (environment variable, secret id, JSON field)
_BINDINGS: tuple[tuple[str, str, str], ...] = (
    ("OPENAI_API_KEY", "openai-api-key", "OPENAI_API_KEY"),
    (
        "SUPABASE_URL",
        "lab-data-integrations-supabase-public",
        "NEXT_PUBLIC_SUPABASE_URL",
    ),
    ("GMAIL_SENDER_EMAIL", "lab-data-integrations-gmail", "GMAIL_SENDER_EMAIL"),
    ("GMAIL_APP_PASSWORD", "lab-data-integrations-gmail", "GMAIL_APP_PASSWORD"),
    (
        "OTEL_EXPORTER_OTLP_HEADERS",
        "lab-data-integrations-interface-grafana-cloud-oltp-header",
        "OTEL_EXPORTER_OTLP_HEADERS",
    ),
)

_OTLP_PREFIX = "Authorization=Basic%20"


def fill_unset_secrets(only: frozenset[str] | None = None) -> None:
    """Set absent variables from Secrets Manager. A name already present wins."""

    pending = _pending(only)
    if not pending:
        return
    if not _aws_credentials_present():
        logger.warning(
            "Left unset because AWS credentials are not in the environment: %s",
            ", ".join(binding[0] for binding in pending),
        )
        return
    client = build_client("secretsmanager", AWS_REGION, None)
    for secret_id in _secret_ids(pending):
        group = [binding for binding in pending if binding[1] == secret_id]
        _apply_group(client, secret_id, group)


def _pending(only: frozenset[str] | None) -> list[tuple[str, str, str]]:
    return [
        binding
        for binding in _BINDINGS
        if (only is None or binding[0] in only) and binding[0] not in os.environ
    ]


def _apply_group(
    client: Any,
    secret_id: str,
    group: list[tuple[str, str, str]],
) -> None:
    payload = _read_object(client, secret_id)
    if payload is None:
        return
    for name, _, field in group:
        _apply(name, secret_id, field, payload.get(field))


def _aws_credentials_present() -> bool:
    return bool(os.environ.get("AWS_ACCESS_KEY_ID", "").strip()) and bool(
        os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
    )


def _secret_ids(pending: list[tuple[str, str, str]]) -> list[str]:
    seen: list[str] = []
    for _, secret_id, _ in pending:
        if secret_id not in seen:
            seen.append(secret_id)
    return seen


def _read_object(client: Any, secret_id: str) -> dict[str, object] | None:
    try:
        response = client.get_secret_value(SecretId=secret_id)
    except ClientError as error:
        logger.warning(
            "Could not read Secrets Manager secret %s (%s).",
            secret_id,
            error_code(error) or "unknown",
        )
        return None
    raw = response.get("SecretString") or ""
    if not isinstance(raw, str):
        logger.info("Secrets Manager secret %s has no string payload.", secret_id)
        return None
    return _parse_object(raw, secret_id)


def _parse_object(raw: str, secret_id: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.info("Secrets Manager secret %s is not JSON.", secret_id)
        return None
    if not isinstance(parsed, dict):
        logger.info("Secrets Manager secret %s is not an object.", secret_id)
        return None
    result: dict[str, object] = {}
    for key, value in parsed.items():
        if isinstance(key, str):
            result[key] = value
    return result


def _apply(name: str, secret_id: str, field: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        logger.info(
            "Secrets Manager secret %s has no string field %s for %s.",
            secret_id,
            field,
            name,
        )
        return
    if not _acceptable(name, value):
        logger.info(
            "Refused to set %s from Secrets Manager secret %s. The value failed the format check.",
            name,
            secret_id,
        )
        return
    os.environ[name] = value
    logger.info("Set %s from Secrets Manager secret %s.", name, secret_id)


def _acceptable(name: str, value: str) -> bool:
    if name == "SUPABASE_URL":
        host = urlparse(value).hostname or ""
        return host.endswith(".supabase.co")
    if name == "OTEL_EXPORTER_OTLP_HEADERS":
        return value.startswith(_OTLP_PREFIX) and " " not in value
    return True
