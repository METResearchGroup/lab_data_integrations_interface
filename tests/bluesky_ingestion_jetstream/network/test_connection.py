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
    event_time_us,
    is_commit,
    process_all_websocket_events,
    process_commit_event,
)
from tests.bluesky_ingestion_jetstream.conftest import (
    CID,
    CREATED_AT,
    DID,
    FOLLOW_COLLECTION,
    INGESTED_AT,
    LIKE_COLLECTION,
    POST_COLLECTION,
    REPOST_COLLECTION,
    REV,
    RKEY,
    SUBJECT_DID,
    SUBJECT_URI,
    TIME_US,
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

    def test_carries_the_cursor_when_there_is_one(self):
        query = parse_qs(urlparse(build_url(TIME_US)).query)

        assert query["cursor"] == [str(TIME_US)]

    def test_omits_the_cursor_on_a_cold_start(self):
        """A cursor param at all would be read as a position, so it has to be absent."""

        assert "cursor" not in parse_qs(urlparse(build_url()).query)

    def test_a_zero_cursor_is_still_sent(self):
        """Falsy but meaningful; only None means "no cursor"."""

        assert parse_qs(urlparse(build_url(0)).query)["cursor"] == ["0"]


class TestEventTimeUs:
    def test_reads_the_brokers_timestamp(self):
        assert event_time_us({"time_us": TIME_US}) == TIME_US

    @pytest.mark.parametrize("time_us", [None, "1725911162329308", True, 1.5, []])
    def test_unusable_timestamps_have_no_position(self, time_us):
        """bools are ints, and a `True` position is junk rather than 1 microsecond."""

        assert event_time_us({"time_us": time_us}) is None

    @pytest.mark.parametrize("event", ["a string", 42, None, []])
    def test_non_dict_frames_have_no_position(self, event):
        assert event_time_us(event) is None

    def test_a_missing_timestamp_has_no_position(self):
        assert event_time_us({"kind": "commit"}) is None


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
                "rev": REV,
                "created_at": CREATED_AT,
                "ingested_at": INGESTED_AT,
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

    @pytest.mark.parametrize("time_us", [None, "1725911162329308", True])
    def test_unusable_time_us_drops_the_row(self, time_us):
        """`ingested_at` is derived from `time_us`, so junk there drops the row.

        It is the one required column the broker supplies rather than the client,
        so a null here means a malformed envelope rather than a careless poster.
        """

        event = make_event(POST_COLLECTION, post_record(), time_us=time_us)

        assert process_commit_event(event) is None

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
        return [event async for event in process_all_websocket_events(aiter_list(messages))]

    def record_types(self, events):
        return [event.parsed[0] for event in events if event.parsed is not None]

    def test_yields_a_row_per_commit(self):
        messages = [json.dumps(make_event(POST_COLLECTION, post_record())) for _ in range(3)]
        events = asyncio.run(self.collect(messages))

        assert self.record_types(events) == ["posts"] * 3

    def test_accepts_bytes_frames(self):
        message = json.dumps(make_event(LIKE_COLLECTION, interaction_record())).encode()
        events = asyncio.run(self.collect([message]))

        assert self.record_types(events) == ["likes"]

    def test_carries_the_position_of_every_event(self):
        message = json.dumps(make_event(LIKE_COLLECTION, interaction_record()))
        events = asyncio.run(self.collect([message]))

        assert [event.time_us for event in events] == [TIME_US]

    @pytest.mark.parametrize("message", ["NOT JSON", "{unclosed", "", "<html>"])
    def test_malformed_json_is_skipped(self, message):
        """One bad frame must not kill the connection and drop the buffers."""

        assert asyncio.run(self.collect([message])) == []

    def test_frames_without_a_position_are_skipped(self):
        """Nothing to record and nothing to store, so there is no event to yield."""

        messages = [json.dumps(make_event(POST_COLLECTION, post_record(), time_us=None))]

        assert asyncio.run(self.collect(messages)) == []

    def test_non_commit_events_are_yielded_unparsed(self):
        """They advance the cursor even though there is nothing to store."""

        messages = [json.dumps({"kind": "identity", "did": DID, "time_us": TIME_US})]
        events = asyncio.run(self.collect(messages))

        assert [(event.time_us, event.parsed) for event in events] == [(TIME_US, None)]

    def test_unstorable_commits_are_yielded_unparsed(self):
        messages = [json.dumps(make_event(POST_COLLECTION, post_record(), operation="delete"))]
        events = asyncio.run(self.collect(messages))

        assert [event.parsed for event in events] == [None]

    def test_bad_frames_do_not_stop_later_good_ones(self):
        messages = [
            "NOT JSON",
            json.dumps({"kind": "identity", "time_us": TIME_US}),
            json.dumps(make_event(POST_COLLECTION, post_record(), operation="delete")),
            json.dumps(make_event(FOLLOW_COLLECTION, follow_record())),
        ]
        events = asyncio.run(self.collect(messages))

        assert self.record_types(events) == ["follows"]

    def test_empty_stream_yields_nothing(self):
        assert asyncio.run(self.collect([])) == []


class TestReconnectBackoff:
    """The retry loop, driven through the real generator with a fake socket."""

    def run_until(self, monkeypatch, messages_per_connection, sleep_limit, error=None):
        """Reconnect repeatedly, returning (yielded events, sleep intervals)."""

        sleeps: list[float] = []
        events: list = []

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
                async for event in c.stream_events():
                    events.append(event)
            except StopLoop:
                pass

        asyncio.run(go())
        return events, sleeps

    def test_backoff_doubles_and_caps(self, monkeypatch):
        _, sleeps = self.run_until(monkeypatch, messages_per_connection=0, sleep_limit=9)

        assert sleeps == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0]
        assert max(sleeps) == MAX_BACKOFF_SECONDS

    def test_backoff_resets_once_rows_flow(self, monkeypatch):
        """A connection that delivered data then died retries immediately."""

        events, sleeps = self.run_until(monkeypatch, messages_per_connection=2, sleep_limit=5)

        assert sleeps == [INITIAL_BACKOFF_SECONDS] * 5
        assert len(events) == 10

    def test_accept_then_drop_does_not_hot_loop(self, monkeypatch):
        """Resetting on connect instead of on data would spin here at full speed."""

        events, sleeps = self.run_until(monkeypatch, messages_per_connection=0, sleep_limit=5)

        assert events == []
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

    def test_each_reconnect_reads_the_cursor_again(self, monkeypatch):
        """Read once at startup instead, and every reconnect replays from the same point."""

        urls: list[str] = []
        cursors = iter([100, 200, 300])
        sleeps: list[float] = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) >= 3:
                raise StopLoop

        def record(url, *args, **kwargs):
            urls.append(url)
            return FakeConnection([])

        monkeypatch.setattr(c.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(c.websockets, "connect", record)

        async def go():
            try:
                async for _ in c.stream_events(lambda: next(cursors)):
                    pass
            except StopLoop:
                pass

        asyncio.run(go())

        assert [parse_qs(urlparse(url).query)["cursor"] for url in urls] == [
            ["100"],
            ["200"],
            ["300"],
        ]

    def test_a_cold_start_connects_without_a_cursor(self, monkeypatch):
        urls: list[str] = []

        async def fake_sleep(seconds):
            raise StopLoop

        def record(url, *args, **kwargs):
            urls.append(url)
            return FakeConnection([])

        monkeypatch.setattr(c.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(c.websockets, "connect", record)

        async def go():
            try:
                async for _ in c.stream_events():
                    pass
            except StopLoop:
                pass

        asyncio.run(go())

        assert "cursor" not in parse_qs(urlparse(urls[0]).query)

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
