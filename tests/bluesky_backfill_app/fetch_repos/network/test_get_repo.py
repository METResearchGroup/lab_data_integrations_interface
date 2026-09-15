import io
import urllib.error

import pytest

from bluesky_backfill_app.fetch_repos.constants import (
    GET_REPO_DEADLINE_SECONDS,
    GET_REPO_MAX_ATTEMPTS,
)
from bluesky_backfill_app.fetch_repos.network.errors import XrpcError
from bluesky_backfill_app.fetch_repos.network.get_repo import build_url, fetch_repo

DID = "did:plc:example"
TAKENDOWN_BODY = '{"error":"RepoTakendown","message":"Repo has been takendown: did:plc:example"}'


class FakeResponse:
    def __init__(self, *chunks):
        self.chunks = list(chunks)

    def read(self, _size):
        return self.chunks.pop(0) if self.chunks else b""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def http_error(code, body=None, headers=None):
    fp = io.BytesIO(body.encode()) if body is not None else None
    return urllib.error.HTTPError("url", code, "boom", headers, fp)


class scripted:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, url, **_):
        self.calls.append(url)
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def test_build_url_encodes_the_did():
    assert build_url("did:plc:abc").endswith("getRepo?did=did%3Aplc%3Aabc")


def test_fetch_repo_joins_the_chunks():
    urlopen = scripted(FakeResponse(b"ab", b"cd"))

    assert fetch_repo(DID, urlopen=urlopen, sleep=lambda _: None) == b"abcd"
    assert len(urlopen.calls) == 1


def test_fetch_repo_retries_a_rate_limit():
    slept = []
    urlopen = scripted(http_error(429), FakeResponse(b"car"))

    assert fetch_repo(DID, urlopen=urlopen, sleep=slept.append) == b"car"
    assert slept == [1.0]


def test_fetch_repo_honours_retry_after():
    slept = []
    urlopen = scripted(http_error(429, headers={"Retry-After": "5"}), FakeResponse(b"car"))

    fetch_repo(DID, urlopen=urlopen, sleep=slept.append)

    assert slept == [5.0]


def test_fetch_repo_raises_a_permanent_error_without_retrying():
    urlopen = scripted(http_error(400, TAKENDOWN_BODY))

    with pytest.raises(XrpcError) as caught:
        fetch_repo(DID, urlopen=urlopen, sleep=lambda _: None)

    assert caught.value.error == "RepoTakendown"
    assert isinstance(caught.value.__cause__, urllib.error.HTTPError)
    assert len(urlopen.calls) == 1


def test_fetch_repo_gives_up_after_max_attempts():
    urlopen = scripted(*[http_error(503) for _ in range(GET_REPO_MAX_ATTEMPTS)])

    with pytest.raises(XrpcError) as caught:
        fetch_repo(DID, urlopen=urlopen, sleep=lambda _: None)

    assert caught.value.status == 503
    assert len(urlopen.calls) == GET_REPO_MAX_ATTEMPTS


def test_fetch_repo_retries_a_transport_failure():
    urlopen = scripted(ConnectionResetError(), FakeResponse(b"car"))

    assert fetch_repo(DID, urlopen=urlopen, sleep=lambda _: None) == b"car"


def test_fetch_repo_reraises_the_last_transport_failure():
    urlopen = scripted(*[urllib.error.URLError("reset") for _ in range(GET_REPO_MAX_ATTEMPTS)])

    with pytest.raises(urllib.error.URLError):
        fetch_repo(DID, urlopen=urlopen, sleep=lambda _: None)


def test_fetch_repo_times_out_a_download_past_the_deadline():
    clock = FakeClock()

    class SlowResponse(FakeResponse):
        def read(self, size):
            clock.now += GET_REPO_DEADLINE_SECONDS
            return super().read(size)

    urlopen = scripted(SlowResponse(b"a", b"b"))

    with pytest.raises(TimeoutError):
        fetch_repo(DID, urlopen=urlopen, sleep=lambda _: None, clock=clock)

    assert len(urlopen.calls) == 1


def test_fetch_repo_stops_retrying_when_the_next_sleep_would_pass_the_deadline():
    clock = FakeClock()

    def urlopen(url, **_):
        clock.now = GET_REPO_DEADLINE_SECONDS - 0.5
        raise http_error(503)

    with pytest.raises(XrpcError):
        fetch_repo(DID, urlopen=urlopen, sleep=pytest.fail, clock=clock)
