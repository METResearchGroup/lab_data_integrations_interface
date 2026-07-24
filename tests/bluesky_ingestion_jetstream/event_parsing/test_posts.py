"""Tests for post column extraction."""

import pytest

from bluesky_ingestion_jetstream.event_parsing.posts import parse_post
from tests.bluesky_ingestion_jetstream.conftest import post_record

POST_COLUMNS = {"text", "langs", "reply_root_uri", "reply_parent_uri", "embed_type"}


class TestHappyPath:
    def test_extracts_every_post_column(self):
        assert parse_post(post_record()) == {
            "text": "hello world",
            "langs": ["en"],
            "reply_root_uri": "at://did:plc:abc/app.bsky.feed.post/3l3qroot",
            "reply_parent_uri": "at://did:plc:def/app.bsky.feed.post/3l3rparent",
            "embed_type": "app.bsky.embed.images",
        }

    def test_returns_exactly_the_post_columns(self):
        """Shared columns are the caller's job; this must not add or drop keys."""

        assert set(parse_post(post_record())) == POST_COLUMNS

    def test_an_empty_record_yields_all_nulls(self):
        assert parse_post({}) == dict.fromkeys(POST_COLUMNS)


class TestReply:
    def test_top_level_post_has_null_reply_uris(self):
        record = post_record()
        del record["reply"]
        row = parse_post(record)

        assert row["reply_root_uri"] is None
        assert row["reply_parent_uri"] is None

    @pytest.mark.parametrize("reply", ["a string", 42, [], None, True])
    def test_reply_of_the_wrong_type_yields_nulls(self, reply):
        """A malformed reply must null the columns, never raise."""

        row = parse_post(post_record(reply=reply))

        assert row["reply_root_uri"] is None
        assert row["reply_parent_uri"] is None

    @pytest.mark.parametrize("root", ["a string", 42, [], None])
    def test_root_of_the_wrong_type_leaves_parent_intact(self, root):
        record = post_record(reply={"root": root, "parent": {"uri": "at://x/y/parent"}})
        row = parse_post(record)

        assert row["reply_root_uri"] is None
        assert row["reply_parent_uri"] == "at://x/y/parent"

    @pytest.mark.parametrize("parent", ["a string", 42, [], None])
    def test_parent_of_the_wrong_type_leaves_root_intact(self, parent):
        record = post_record(reply={"root": {"uri": "at://x/y/root"}, "parent": parent})
        row = parse_post(record)

        assert row["reply_root_uri"] == "at://x/y/root"
        assert row["reply_parent_uri"] is None

    @pytest.mark.parametrize("uri", [42, None, [], {}])
    def test_reply_uri_of_the_wrong_type_is_null(self, uri):
        record = post_record(reply={"root": {"uri": uri}, "parent": {"uri": uri}})
        row = parse_post(record)

        assert row["reply_root_uri"] is None
        assert row["reply_parent_uri"] is None


class TestEmbed:
    def test_extracts_the_discriminator_only(self):
        record = post_record(embed={"$type": "app.bsky.embed.video", "video": {"size": 1}})

        assert parse_post(record)["embed_type"] == "app.bsky.embed.video"

    def test_missing_embed_is_null(self):
        record = post_record()
        del record["embed"]

        assert parse_post(record)["embed_type"] is None

    @pytest.mark.parametrize("embed", ["a string", 42, [], None, True])
    def test_embed_of_the_wrong_type_is_null(self, embed):
        assert parse_post(post_record(embed=embed))["embed_type"] is None

    def test_embed_without_a_type_is_null(self):
        assert parse_post(post_record(embed={"images": []}))["embed_type"] is None


class TestTextAndLangs:
    @pytest.mark.parametrize("text", [42, None, [], {}, True])
    def test_text_of_the_wrong_type_is_null(self, text):
        assert parse_post(post_record(text=text))["text"] is None

    def test_empty_text_is_kept(self):
        """An empty post body is real data, not a missing value."""

        assert parse_post(post_record(text=""))["text"] == ""

    def test_multiple_langs_are_kept(self):
        assert parse_post(post_record(langs=["en", "ja"]))["langs"] == ["en", "ja"]

    def test_langs_drops_non_string_members(self):
        assert parse_post(post_record(langs=["en", 42, None]))["langs"] == ["en"]

    @pytest.mark.parametrize("langs", ["en", 42, None, {}, True])
    def test_langs_of_the_wrong_type_is_null(self, langs):
        assert parse_post(post_record(langs=langs))["langs"] is None
