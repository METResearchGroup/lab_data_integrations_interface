"""AWS ClientError code constants and lookup."""

from __future__ import annotations

from botocore.exceptions import ClientError

CONDITIONAL_CHECK_FAILED = "ConditionalCheckFailedException"


def error_code(error: ClientError) -> str:
    """Return the AWS error code string from a ClientError, or empty if absent."""

    return error.response.get("Error", {}).get("Code", "")
