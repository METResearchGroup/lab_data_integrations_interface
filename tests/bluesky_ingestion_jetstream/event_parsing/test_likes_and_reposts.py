"""Tests for like and repost column extraction."""

import pytest

from bluesky_ingestion_jetstream.event_parsing.likes_and_reposts import parse_like_or_repost
from tests.bluesky_ingestion_jetstream.conftest import (
    SUBJECT_CID,
    SUBJECT_URI,
    interaction_record,
)

INTERACTION_COLUMNS = {"subject_uri", "subject_cid"}


class TestHappyPath:
    def test_extracts_the_strongref_subject(self):
        assert parse_like_or_repost(interaction_record()) == {
            "subject_uri": SUBJECT_URI,
            "subject_cid": SUBJECT_CID,
        }

    def test_returns_exactly_the_interaction_columns(self):
        assert set(parse_like_or_repost(interaction_record())) == INTERACTION_COLUMNS

    def test_an_empty_record_yields_all_nulls(self):
        assert parse_like_or_repost({}) == dict.fromkeys(INTERACTION_COLUMNS)

    def test_likes_and_reposts_parse_identically(self):
        """Identical record shapes, so one function serves both tables."""

        record = interaction_record()

        assert parse_like_or_repost(record) == parse_like_or_repost(dict(record))


class TestSubject:
    def test_missing_subject_yields_nulls(self):
        record = interaction_record()
        del record["subject"]
        row = parse_like_or_repost(record)

        assert row["subject_uri"] is None
        assert row["subject_cid"] is None

    @pytest.mark.parametrize("subject", ["a bare did string", 42, [], None, True])
    def test_subject_of_the_wrong_type_yields_nulls(self, subject):
        """A bare string here is the follows shape; it must not half-parse."""

        row = parse_like_or_repost(interaction_record(subject=subject))

        assert row["subject_uri"] is None
        assert row["subject_cid"] is None

    def test_subject_without_cid_keeps_the_uri(self):
        """`subject_cid` is nullable; a missing one must not drop the join key."""

        row = parse_like_or_repost(interaction_record(subject={"uri": SUBJECT_URI}))

        assert row["subject_uri"] == SUBJECT_URI
        assert row["subject_cid"] is None

    def test_subject_without_uri_keeps_the_cid(self):
        row = parse_like_or_repost(interaction_record(subject={"cid": SUBJECT_CID}))

        assert row["subject_uri"] is None
        assert row["subject_cid"] == SUBJECT_CID

    @pytest.mark.parametrize("value", [42, None, [], {}, True])
    def test_subject_fields_of_the_wrong_type_are_null(self, value):
        record = interaction_record(subject={"uri": value, "cid": value})
        row = parse_like_or_repost(record)

        assert row["subject_uri"] is None
        assert row["subject_cid"] is None
