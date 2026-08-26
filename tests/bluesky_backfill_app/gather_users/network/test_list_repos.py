import json
import urllib.error

import pytest

from bluesky_backfill_app.gather_users.constants import MAX_BACKOFF_SECONDS
from bluesky_backfill_app.gather_users.network.list_repos import (
    RepoPage,
    backoff_seconds,
    build_url,
    fetch_page,
    is_active,
    iter_pages,
    parse_page,
    retry_delay,
)

LIST_REPOS = "bluesky_backfill_app.gather_users.network.list_repos"


class FakeResponse:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode()

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def json_response(payload):
    return FakeResponse(payload)


def http_error(code, headers=None):
    return urllib.error.HTTPError("url", code, "boom", headers, None)


def page_payload(dids, cursor=None):
    return {"repos": [{"did": did} for did in dids], "cursor": cursor}


def test_build_url_omits_a_missing_cursor():
    assert "cursor" not in build_url(None, 500)
    assert "limit=500" in build_url(None, 500)


def test_build_url_encodes_the_cursor():
    assert "cursor=a%2Fb" in build_url("a/b", 10)


def test_parse_page_extracts_dids_and_cursor():
    page = parse_page(page_payload(["did:plc:a", "did:plc:b"], cursor="next"))

    assert page == RepoPage(dids=["did:plc:a", "did:plc:b"], cursor="next")


def test_parse_page_handles_a_final_page():
    assert parse_page({"repos": []}).cursor is None


@pytest.mark.parametrize("payload", [{}, {"repos": None}, {"repos": "nope"}])
def test_parse_page_tolerates_a_malformed_body(payload):
    assert parse_page(payload) == RepoPage(dids=[], cursor=None)


def test_parse_page_skips_entries_without_a_did():
    payload = {"repos": [{"did": "did:plc:a"}, {}, "junk", {"did": ""}]}

    assert parse_page(payload).dids == ["did:plc:a"]


def test_parse_page_skips_inactive_repos():
    payload = {
        "repos": [
            {"did": "did:plc:a", "active": True},
            {"did": "did:plc:b", "active": False, "status": "takendown"},
            {"did": "did:plc:c", "active": False, "status": "deactivated"},
        ]
    }

    assert parse_page(payload).dids == ["did:plc:a"]


def test_parse_page_keeps_a_repo_with_no_active_field():
    """The relay always sends `active`; absence is not a reason to drop a DID."""

    assert parse_page({"repos": [{"did": "did:plc:a"}]}).dids == ["did:plc:a"]


@pytest.mark.parametrize(
    ("repo", "expected"),
    [
        ({"active": True}, True),
        ({}, True),
        ({"active": None}, True),
        ({"active": False}, False),
    ],
)
def test_is_active(repo, expected):
    assert is_active(repo) is expected


def test_parse_page_ignores_a_non_string_cursor():
    assert parse_page({"repos": [], "cursor": 5}).cursor is None


def test_fetch_page_returns_the_first_success():
    calls = []

    def urlopen(url, **_):
        calls.append(url)
        return json_response(page_payload(["did:plc:a"], cursor="next"))

    page = fetch_page(None, urlopen=urlopen, sleep=lambda _: None)

    assert page.dids == ["did:plc:a"]
    assert len(calls) == 1


def test_fetch_page_retries_a_rate_limit():
    responses = [http_error(429), json_response(page_payload(["did:plc:a"]))]
    slept = []

    def urlopen(url, **_):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    page = fetch_page(None, urlopen=urlopen, sleep=slept.append)

    assert page.dids == ["did:plc:a"]
    assert slept == [1.0]


def test_fetch_page_honours_retry_after():
    responses = [http_error(429, {"Retry-After": "5"}), json_response(page_payload([]))]
    slept = []

    def urlopen(url, **_):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    fetch_page(None, urlopen=urlopen, sleep=slept.append)

    assert slept == [5.0]


def test_fetch_page_reraises_a_non_retryable_status():
    def urlopen(url, **_):
        raise http_error(400)

    with pytest.raises(urllib.error.HTTPError):
        fetch_page(None, urlopen=urlopen, sleep=lambda _: None)


def test_fetch_page_gives_up_after_max_attempts():
    calls = []

    def urlopen(url, **_):
        calls.append(url)
        raise http_error(503)

    with pytest.raises(urllib.error.HTTPError):
        fetch_page(None, urlopen=urlopen, sleep=lambda _: None)

    assert len(calls) == 5


def test_fetch_page_retries_a_transport_failure():
    responses = [urllib.error.URLError("reset"), json_response(page_payload(["did:plc:a"]))]

    def urlopen(url, **_):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    assert fetch_page(None, urlopen=urlopen, sleep=lambda _: None).dids == ["did:plc:a"]


def test_backoff_doubles_and_caps():
    assert backoff_seconds(0) == 1.0
    assert backoff_seconds(1) == 2.0
    assert backoff_seconds(2) == 4.0
    assert backoff_seconds(20) == MAX_BACKOFF_SECONDS


@pytest.mark.parametrize("header", [None, "soon", ""])
def test_retry_delay_falls_back_to_backoff(header):
    headers = {"Retry-After": header} if header is not None else {}

    assert retry_delay(http_error(429, headers), 1) == 2.0


def test_retry_delay_caps_a_long_retry_after():
    assert retry_delay(http_error(429, {"Retry-After": "9999"}), 0) == MAX_BACKOFF_SECONDS


def test_iter_pages_follows_the_cursor_then_stops(monkeypatch):
    pages = [
        RepoPage(dids=["did:plc:a"], cursor="one"),
        RepoPage(dids=["did:plc:b"], cursor="two"),
        RepoPage(dids=["did:plc:c"], cursor=None),
    ]
    seen_cursors = []

    def fake_fetch(cursor):
        seen_cursors.append(cursor)
        return pages[len(seen_cursors) - 1]

    monkeypatch.setattr(f"{LIST_REPOS}.fetch_page", fake_fetch)

    assert list(iter_pages(None)) == pages
    assert seen_cursors == [None, "one", "two"]
