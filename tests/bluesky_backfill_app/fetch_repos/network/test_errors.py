import http.client
import io
import json
import urllib.error
from pathlib import Path

import pytest

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
from bluesky_backfill_app.fetch_repos.network.errors import XrpcError, classify

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "get_repo_errors.json").read_text())


def http_error(code, body=None):
    fp = io.BytesIO(body.encode()) if body is not None else None
    return urllib.error.HTTPError("url", code, "boom", None, fp)


def fixture_error(name):
    return http_error(FIXTURES[name]["status"], FIXTURES[name]["body"])


def test_xrpc_error_parses_the_body():
    error = XrpcError.from_http_error(fixture_error("account_deactivated"))

    assert (error.status, error.error) == (400, "RepoDeactivated")
    assert error.message == "Repo has been deactivated: did:plc:example"


@pytest.mark.parametrize("body", ["<html>bad gateway</html>", "[1, 2]", ""])
def test_xrpc_error_keeps_a_body_without_an_error_code(body):
    error = XrpcError.from_http_error(http_error(502, body))

    assert (error.status, error.error, error.message) == (502, None, body)


def test_xrpc_error_tolerates_a_missing_body():
    error = XrpcError.from_http_error(http_error(500))

    assert (error.status, error.error, error.message) == (500, None, "")


def test_xrpc_error_repr_carries_the_code_and_message():
    assert "RepoTakendown" in repr(XrpcError.from_http_error(fixture_error("account_takendown")))


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("account_deactivated", REASON_ACCOUNT_DEACTIVATED),
        ("account_takendown", REASON_ACCOUNT_TAKENDOWN),
        ("account_deleted", REASON_REPO_NOT_FOUND),
        ("did_not_found", REASON_REPO_NOT_FOUND),
        ("did_invalid", REASON_UNKNOWN),
    ],
)
def test_classify_fixtures(fixture, expected):
    assert classify(XrpcError.from_http_error(fixture_error(fixture))) == expected


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (XrpcError(429, None, ""), REASON_HTTP_429),
        (XrpcError(500, None, ""), REASON_HTTP_5XX),
        (XrpcError(503, "RepoNotFound", ""), REASON_HTTP_5XX),
        (XrpcError(400, None, ""), REASON_UNKNOWN),
        (XrpcError(400, "RepoSuspended", ""), REASON_UNKNOWN),
        (TimeoutError(), REASON_TIMEOUT),
        (urllib.error.URLError(TimeoutError()), REASON_TIMEOUT),
        (urllib.error.URLError("reset"), REASON_CONNECTION_ERROR),
        (ConnectionResetError(), REASON_CONNECTION_ERROR),
        (http.client.IncompleteRead(b""), REASON_CONNECTION_ERROR),
        (ValueError(), REASON_UNKNOWN),
    ],
)
def test_classify(error, expected):
    assert classify(error) == expected
