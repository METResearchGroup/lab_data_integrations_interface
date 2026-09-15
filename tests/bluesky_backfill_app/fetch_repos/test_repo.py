import pytest

from bluesky_backfill_app.aws.constants import (
    REASON_ACCOUNT_TAKENDOWN,
    REASON_CAR_DECODE_ERROR,
    REASON_SCHEMA_MISMATCH,
    REASON_TIMEOUT,
)
from bluesky_backfill_app.fetch_repos.failures import RepoFailure
from bluesky_backfill_app.fetch_repos.network.errors import XrpcError
from bluesky_backfill_app.fetch_repos.repo import load_repo
from bluesky_ingestion_jetstream.constants import LIKES, POSTS

REPO = "bluesky_backfill_app.fetch_repos.repo"
DID = "did:plc:example"
ROWS = {LIKES: [{"uri": f"at://{DID}/app.bsky.feed.like/1", "did": DID}]}


def raise_(error):
    def fail(*_args):
        raise error

    return fail


@pytest.fixture
def fetched(monkeypatch):
    monkeypatch.setattr(f"{REPO}.fetch_repo", lambda did: b"car")
    monkeypatch.setattr(f"{REPO}.decode", lambda did, car, ingested_at: ROWS)


def test_load_repo_returns_the_rows(fetched):
    assert load_repo(DID) == ROWS


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (XrpcError(400, "RepoTakendown", ""), REASON_ACCOUNT_TAKENDOWN),
        (TimeoutError(), REASON_TIMEOUT),
    ],
)
def test_load_repo_classifies_a_fetch_failure(monkeypatch, error, reason):
    monkeypatch.setattr(f"{REPO}.fetch_repo", raise_(error))

    with pytest.raises(RepoFailure) as caught:
        load_repo(DID)

    assert (caught.value.reason, caught.value.error) == (reason, error)


def test_load_repo_reports_a_decode_failure(fetched, monkeypatch):
    error = ValueError("bad car")
    monkeypatch.setattr(f"{REPO}.decode", raise_(error))

    with pytest.raises(RepoFailure) as caught:
        load_repo(DID)

    assert (caught.value.reason, caught.value.error) == (REASON_CAR_DECODE_ERROR, error)


def test_load_repo_reports_a_row_that_does_not_fit_the_schema(fetched, monkeypatch):
    rows = {POSTS: [{"uri": "at://x", "text": 5}]}
    monkeypatch.setattr(f"{REPO}.decode", lambda did, car, ingested_at: rows)

    with pytest.raises(RepoFailure) as caught:
        load_repo(DID)

    assert caught.value.reason == REASON_SCHEMA_MISMATCH
