import http.client
import json
import urllib.error

from bluesky_backfill_app.aws.constants import (
    REASON_ACCOUNT_DEACTIVATED,
    REASON_ACCOUNT_TAKENDOWN,
    REASON_CONNECTION_ERROR,
    REASON_HTTP_5XX,
    REASON_HTTP_429,
    REASON_REPO_NOT_FOUND,
    REASON_TIMEOUT,
    REASON_UNKNOWN,
)
from bluesky_backfill_app.fetch_repos.constants import MAX_ERROR_BODY_BYTES

TRANSPORT_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException)

XRPC_ERROR_TO_REASON = {
    "RepoDeactivated": REASON_ACCOUNT_DEACTIVATED,
    "RepoTakendown": REASON_ACCOUNT_TAKENDOWN,
    "RepoNotFound": REASON_REPO_NOT_FOUND,
}


class XrpcError(Exception):
    def __init__(self, status: int, error: str | None, message: str):
        super().__init__(status, error, message)
        self.status = status
        self.error = error
        self.message = message

    @classmethod
    def from_http_error(cls, http_error: urllib.error.HTTPError) -> "XrpcError":
        try:
            body = http_error.fp.read(MAX_ERROR_BODY_BYTES) if http_error.fp else b""
        except (OSError, http.client.HTTPException):
            body = b""
        text = body.decode("utf-8", errors="replace")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if not isinstance(payload, dict):
            return cls(http_error.code, None, text)
        error = payload.get("error")
        message = payload.get("message")
        return cls(
            http_error.code,
            error if isinstance(error, str) else None,
            message if isinstance(message, str) else text,
        )


def classify(error: BaseException) -> str:
    if isinstance(error, XrpcError):
        if error.status == 429:
            return REASON_HTTP_429
        if 500 <= error.status < 600:
            return REASON_HTTP_5XX
        return XRPC_ERROR_TO_REASON.get(error.error or "", REASON_UNKNOWN)
    if isinstance(error, TimeoutError):
        return REASON_TIMEOUT
    if isinstance(error, urllib.error.URLError) and isinstance(error.reason, TimeoutError):
        return REASON_TIMEOUT
    if isinstance(error, TRANSPORT_ERRORS):
        return REASON_CONNECTION_ERROR
    return REASON_UNKNOWN
