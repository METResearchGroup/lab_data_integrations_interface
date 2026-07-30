"""Tests for follow column extraction."""

import pytest

from bluesky_ingestion_jetstream.event_parsing.follows import parse_follow
from tests.bluesky_ingestion_jetstream.conftest import SUBJECT_DID, SUBJECT_URI, follow_record


class TestHappyPath:
    def test_extracts_the_bare_did_subject(self):
        """Follows put a bare DID in `subject` where likes put a strongref object.

        Written by copying the likes parser, this silently nulls every follow, so
        it is the regression that matters most in this module.
        """

        assert parse_follow(follow_record()) == {"subject_did": SUBJECT_DID}

    def test_returns_exactly_the_follow_column(self):
        assert set(parse_follow(follow_record())) == {"subject_did"}

    def test_an_empty_record_yields_a_null(self):
        assert parse_follow({}) == {"subject_did": None}


class TestSubject:
    def test_missing_subject_is_null(self):
        record = follow_record()
        del record["subject"]

        assert parse_follow(record)["subject_did"] is None

    def test_strongref_subject_is_null(self):
        """The inverse trap: a likes-shaped subject is not a DID."""

        record = follow_record(subject={"uri": SUBJECT_URI, "cid": "bafyx"})

        assert parse_follow(record)["subject_did"] is None

    @pytest.mark.parametrize("subject", [42, None, [], {}, True])
    def test_subject_of_the_wrong_type_is_null(self, subject):
        assert parse_follow(follow_record(subject=subject))["subject_did"] is None

    def test_any_string_subject_is_kept_verbatim(self):
        """Validation of DID shape is not this function's job."""

        assert parse_follow(follow_record(subject="not-a-did"))["subject_did"] == "not-a-did"
