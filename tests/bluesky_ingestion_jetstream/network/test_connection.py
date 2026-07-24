"""Tests for URL building, commit routing, and the reconnect loop."""

import asyncio
import json
from urllib.parse import parse_qs, urlparse

import pytest

from bluesky_ingestion_jetstream.constants import (
    INITIAL_BACKOFF_SECONDS,
    JETSTREAM_ENDPOINT,
    MAX_BACKOFF_SECONDS,
    RECORD_TYPES,
    WANTED_COLLECTIONS,
)
from bluesky_ingestion_jetstream.network import connection as c
from bluesky_ingestion_jetstream.network.connection import (
    build_url,
    is_commit,
    process_all_websocket_events,
    process_commit_event,
)
from tests.bluesky_ingestion_jetstream.conftest import (
    CID,
    CREATED_AT,
    DID,
    FOLLOW_COLLECTION,
    LIKE_COLLECTION,
    POST_COLLECTION,
    REPOST_COLLECTION,
    RKEY,
    SUBJECT_DID,
    SUBJECT_URI,
    follow_record,
    interaction_record,
    make_event,
    post_record,
)


class StopLoop(Exception):
    """Breaks out of the otherwise-infinite reconnect loop."""


async def aiter_list(items):
    for item in items:
        yield item


class FakeConnection:
    """An `async with`-able socket that yields messages then drops."""

    def __init__(self, messages, error=OSError("dropped")):
        self.messages = messages
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def __aiter__(self):
        for message in self.messages:
            yield message
        raise self.error


class TestBuildUrl:
    def test_points_at_the_jetstream_endpoint(self):
        assert build_url().startswith(JETSTREAM_ENDPOINT)

    def test_requests_every_wanted_collection(self):
        """Filtering server-side keeps the rest of the firehose off the wire."""

        query = parse_qs(urlparse(build_url()).query)

        assert query["wantedCollections"] == list(WANTED_COLLECTIONS)

    def test_requests_exactly_four_collections(self):
        query = parse_qs(urlparse(build_url()).query)

        assert len(query["wantedCollections"]) == len(RECORD_TYPES)


class TestIsCommit:
    def test_true_for_a_commit(self):
        assert is_commit({"kind": "commit"}) is True

    @pytest.mark.parametrize("kind", ["identity", "account", "", None])
    def test_false_for_other_kinds(self, kind):
        assert is_commit({"kind": kind}) is False

    def test_false_when_kind_is_absent(self):
        assert is_commit({"did": "did:plc:x"}) is False

    @pytest.mark.parametrize("event", ["a string", 42, None, [], True])
    def test_false_for_non_dicts(self, event):
        """json.loads can return a list or a scalar for valid-but-wrong JSON."""

        assert is_commit(event) is False


class TestProcessCommitEvent:
    @pytest.mark.parametrize(
        ("collection", "record", "expected"),
        [
            (POST_COLLECTION, post_record(), "posts"),
            (LIKE_COLLECTION, interaction_record(), "likes"),
            (REPOST_COLLECTION, interaction_record(), "reposts"),
            (FOLLOW_COLLECTION, follow_record(), "follows"),
        ],
    )
    def test_each_collection_routes_to_its_record_type(self, collection, record, expected):
        parsed = process_commit_event(make_event(collection, record))

        assert parsed is not None
        assert parsed[0] == expected

    def test_merges_shared_and_type_columns(self):
        parsed = process_commit_event(make_event(FOLLOW_COLLECTION, follow_record()))

        assert parsed == (
            "follows",
            {
                "uri": f"at://{DID}/{FOLLOW_COLLECTION}/{RKEY}",
                "did": DID,
                "cid": CID,
                "created_at": CREATED_AT,
                "subject_did": SUBJECT_DID,
            },
        )

    @pytest.mark.parametrize("operation", ["delete", "update", "", None, 42])
    def test_non_create_operations_are_dropped(self, operation):
        """`delete` is the deleted-post case; we store creates only."""

        event = make_event(POST_COLLECTION, post_record(), operation=operation)

        assert process_commit_event(event) is None

    @pytest.mark.parametrize(
        "collection",
        ["app.bsky.graph.block", "app.bsky.actor.profile", "app.bsky.feed.postgres", ""],
    )
    def test_unknown_collections_are_dropped(self, collection):
        assert process_commit_event(make_event(collection, post_record())) is None

    @pytest.mark.parametrize("collection", [None, 42, [], {}])
    def test_collections_of_the_wrong_type_are_dropped(self, collection):
        """An unhashable collection would raise if passed straight to dict.get."""

        assert process_commit_event(make_event(collection, post_record())) is None

    @pytest.mark.parametrize("commit", ["a string", 42, None, [], True])
    def test_malformed_commits_are_dropped(self, commit, post_event):
        post_event["commit"] = commit

        assert process_commit_event(post_event) is None

    def test_missing_commit_is_dropped(self):
        assert process_commit_event({"kind": "commit", "did": DID}) is None

    def test_empty_event_is_dropped(self):
        assert process_commit_event({}) is None


class TestValidationGate:
    """Rows missing a required column are dropped rather than written as null."""

    @pytest.mark.parametrize("did", [None, ""])
    def test_missing_did_drops_the_row(self, did):
        event = make_event(POST_COLLECTION, post_record(), did=did)

        assert process_commit_event(event) is None

    @pytest.mark.parametrize("rkey", [None, ""])
    def test_missing_rkey_drops_the_row(self, rkey):
        event = make_event(POST_COLLECTION, post_record(), rkey=rkey)

        assert process_commit_event(event) is None

    def test_missing_created_at_drops_the_row(self):
        record = post_record()
        del record["createdAt"]

        assert process_commit_event(make_event(POST_COLLECTION, record)) is None

    def test_unparseable_created_at_drops_the_row(self):
        record = post_record(createdAt="not a timestamp")

        assert process_commit_event(make_event(POST_COLLECTION, record)) is None

    def test_like_without_subject_uri_drops_the_row(self):
        record = interaction_record(subject={"cid": "bafyx"})

        assert process_commit_event(make_event(LIKE_COLLECTION, record)) is None

    def test_follow_without_subject_did_drops_the_row(self):
        record = follow_record(subject={"uri": SUBJECT_URI})

        assert process_commit_event(make_event(FOLLOW_COLLECTION, record)) is None

    def test_missing_cid_is_allowed(self):
        """`cid` is not a required key, so a null one must still be stored."""

        parsed = process_commit_event(make_event(POST_COLLECTION, post_record(), cid=None))

        assert parsed is not None
        assert parsed[1]["cid"] is None

    def test_post_without_text_is_allowed(self):
        record = post_record()
        del record["text"]
        parsed = process_commit_event(make_event(POST_COLLECTION, record))

        assert parsed is not None
        assert parsed[1]["text"] is None


class TestProcessAllWebsocketEvents:
    async def collect(self, messages):
        return [parsed async for parsed in process_all_websocket_events(aiter_list(messages))]

    def test_yields_a_row_per_commit(self):
        messages = [json.dumps(make_event(POST_COLLECTION, post_record())) for _ in range(3)]
        parsed = asyncio.run(self.collect(messages))

        assert [record_type for record_type, _ in parsed] == ["posts"] * 3

    def test_accepts_bytes_frames(self):
        message = json.dumps(make_event(LIKE_COLLECTION, interaction_record())).encode()
        parsed = asyncio.run(self.collect([message]))

        assert [record_type for record_type, _ in parsed] == ["likes"]

    @pytest.mark.parametrize("message", ["NOT JSON", "{unclosed", "", "<html>"])
    def test_malformed_json_is_skipped(self, message):
        """One bad frame must not kill the connection and drop the buffers."""

        assert asyncio.run(self.collect([message])) == []

    def test_non_commit_events_are_skipped(self):
        messages = [json.dumps({"kind": "identity", "did": DID})]

        assert asyncio.run(self.collect(messages)) == []

    def test_unstorable_commits_are_skipped(self):
        messages = [json.dumps(make_event(POST_COLLECTION, post_record(), operation="delete"))]

        assert asyncio.run(self.collect(messages)) == []

    def test_bad_frames_do_not_stop_later_good_ones(self):
        messages = [
            "NOT JSON",
            json.dumps({"kind": "identity"}),
            json.dumps(make_event(POST_COLLECTION, post_record(), operation="delete")),
            json.dumps(make_event(FOLLOW_COLLECTION, follow_record())),
        ]
        parsed = asyncio.run(self.collect(messages))

        assert [record_type for record_type, _ in parsed] == ["follows"]

    def test_empty_stream_yields_nothing(self):
        assert asyncio.run(self.collect([])) == []


class TestReconnectBackoff:
    """The retry loop, driven through the real generator with a fake socket."""

    def run_until(self, monkeypatch, messages_per_connection, sleep_limit, error=None):
        """Reconnect repeatedly, returning (yielded rows, sleep intervals)."""

        sleeps: list[float] = []
        rows: list[tuple[str, dict]] = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) >= sleep_limit:
                raise StopLoop

        messages = [json.dumps(make_event(POST_COLLECTION, post_record()))] * (
            messages_per_connection
        )
        monkeypatch.setattr(c.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(
            c.websockets,
            "connect",
            lambda *a, **k: FakeConnection(messages, error or OSError("dropped")),
        )

        async def go():
            try:
                async for parsed in c.stream_events():
                    rows.append(parsed)
            except StopLoop:
                pass

        asyncio.run(go())
        return rows, sleeps

    def test_backoff_doubles_and_caps(self, monkeypatch):
        _, sleeps = self.run_until(monkeypatch, messages_per_connection=0, sleep_limit=9)

        assert sleeps == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0]
        assert max(sleeps) == MAX_BACKOFF_SECONDS

    def test_backoff_resets_once_rows_flow(self, monkeypatch):
        """A connection that delivered data then died retries immediately."""

        rows, sleeps = self.run_until(monkeypatch, messages_per_connection=2, sleep_limit=5)

        assert sleeps == [INITIAL_BACKOFF_SECONDS] * 5
        assert len(rows) == 10

    def test_accept_then_drop_does_not_hot_loop(self, monkeypatch):
        """Resetting on connect instead of on data would spin here at full speed."""

        rows, sleeps = self.run_until(monkeypatch, messages_per_connection=0, sleep_limit=5)

        assert rows == []
        assert sleeps == [1.0, 2.0, 4.0, 8.0, 16.0]

    def test_websocket_errors_are_retried(self, monkeypatch):
        from websockets.exceptions import ConnectionClosedError

        _, sleeps = self.run_until(
            monkeypatch,
            messages_per_connection=0,
            sleep_limit=3,
            error=ConnectionClosedError(None, None),
        )

        assert sleeps == [1.0, 2.0, 4.0]

    def test_connect_failures_are_retried(self, monkeypatch):
        """A refused connection never yields a socket at all."""

        sleeps: list[float] = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) >= 3:
                raise StopLoop

        def refuse(*args, **kwargs):
            raise OSError("connection refused")

        monkeypatch.setattr(c.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(c.websockets, "connect", refuse)

        async def go():
            try:
                async for _ in c.stream_events():
                    pass
            except StopLoop:
                pass

        asyncio.run(go())

        assert sleeps == [1.0, 2.0, 4.0]

    def test_parsing_bugs_are_not_swallowed(self, monkeypatch):
        """A blanket `except Exception` would retry a code bug forever."""

        def boom(event):
            raise ValueError("bug in the parsing path")

        monkeypatch.setattr(c, "process_commit_event", boom)
        message = json.dumps(make_event(POST_COLLECTION, post_record()))
        monkeypatch.setattr(c.websockets, "connect", lambda *a, **k: FakeConnection([message]))

        async def go():
            async for _ in c.stream_events():
                pass

        with pytest.raises(ValueError, match="bug in the parsing path"):
            asyncio.run(go())
