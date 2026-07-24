"""Tests for the shared commit columns and the defensive access helpers."""

from datetime import UTC, datetime, timedelta

import pytest

from bluesky_ingestion_jetstream.event_parsing.shared import (
    as_dict,
    as_str,
    as_str_list,
    parse_created_at,
    parse_shared,
    validate_non_null_fields,
)
from tests.bluesky_ingestion_jetstream.conftest import (
    CID,
    CREATED_AT,
    CREATED_AT_STR,
    DID,
    POST_COLLECTION,
    RKEY,
    make_event,
    post_record,
)


class TestAsDict:
    def test_returns_a_dict_unchanged(self):
        value = {"a": 1}

        assert as_dict(value) is value

    def test_empty_dict_is_returned_unchanged(self):
        assert as_dict({}) == {}

    @pytest.mark.parametrize("value", ["a string", 42, None, [], True, 1.5])
    def test_non_dicts_become_an_empty_dict(self, value):
        """Client junk must yield null columns downstream, not an AttributeError."""

        assert as_dict(value) == {}


class TestAsStr:
    @pytest.mark.parametrize("value", ["hello", ""])
    def test_returns_a_string_unchanged(self, value):
        assert as_str(value) == value

    @pytest.mark.parametrize("value", [42, None, [], {}, True, 1.5])
    def test_non_strings_become_none(self, value):
        assert as_str(value) is None


class TestAsStrList:
    def test_returns_the_string_members(self):
        assert as_str_list(["en", "ja"]) == ["en", "ja"]

    def test_empty_list_stays_empty(self):
        assert as_str_list([]) == []

    def test_drops_non_string_members(self):
        assert as_str_list(["en", 42, None, {}, "ja"]) == ["en", "ja"]

    def test_all_members_dropped_yields_empty_list(self):
        assert as_str_list([1, 2, 3]) == []

    @pytest.mark.parametrize("value", ["en", 42, None, {"0": "en"}, True])
    def test_non_lists_become_none(self, value):
        assert as_str_list(value) is None


class TestParseCreatedAt:
    def test_parses_a_zulu_timestamp(self):
        assert parse_created_at(CREATED_AT_STR) == CREATED_AT

    def test_naive_timestamp_is_treated_as_utc(self):
        assert parse_created_at("2026-07-23T06:48:11.102") == CREATED_AT

    def test_offset_timestamp_is_converted_to_utc(self):
        assert parse_created_at("2026-07-23T08:48:11.102+02:00") == CREATED_AT

    def test_result_is_always_utc(self):
        parsed = parse_created_at("2026-07-23T08:48:11.102+02:00")

        assert parsed is not None
        assert parsed.tzinfo == UTC

    @pytest.mark.parametrize("value", [42, None, [], {}, True])
    def test_non_strings_become_none(self, value):
        assert parse_created_at(value) is None

    @pytest.mark.parametrize("value", ["not a timestamp", "", "2026-13-45T99:99:99Z", "2026"])
    def test_unparseable_strings_become_none(self, value):
        assert parse_created_at(value) is None

    def test_iso_basic_format_is_accepted(self):
        """Python 3.11's fromisoformat takes the compact form, not just the extended one."""

        assert parse_created_at("20260723") == datetime(2026, 7, 23, tzinfo=UTC)


class TestParseShared:
    def test_extracts_every_common_column(self, post_event):
        row = parse_shared(post_event)

        assert row == {
            "uri": f"at://{DID}/{POST_COLLECTION}/{RKEY}",
            "did": DID,
            "cid": CID,
            "created_at": CREATED_AT,
        }

    def test_uri_is_reconstructed_from_the_parts(self, post_event):
        """`uri` is not on the wire -- Jetstream sends did, collection, and rkey."""

        assert parse_shared(post_event)["uri"] == f"at://{DID}/{POST_COLLECTION}/{RKEY}"

    def test_cid_comes_from_the_commit_not_the_record(self):
        event = make_event(POST_COLLECTION, post_record(cid="record-level-cid"), cid="commit-cid")

        assert parse_shared(event)["cid"] == "commit-cid"

    @pytest.mark.parametrize(
        ("collection", "did", "rkey"),
        [
            (POST_COLLECTION, None, RKEY),
            (POST_COLLECTION, DID, None),
            ("", DID, RKEY),
            (POST_COLLECTION, "", RKEY),
            (POST_COLLECTION, DID, ""),
        ],
    )
    def test_uri_is_none_when_any_part_is_missing(self, collection, did, rkey):
        """A missing part must not produce the string 'at://None/None/None'."""

        row = parse_shared(make_event(collection, post_record(), did=did, rkey=rkey))

        assert row["uri"] is None

    def test_uri_is_none_when_every_part_is_missing(self):
        event = make_event("", post_record(), did=None, rkey=None)

        assert parse_shared(event)["uri"] is None

    def test_missing_commit_yields_all_nulls_but_did(self):
        event = make_event(POST_COLLECTION, post_record(), drop_commit=True)
        row = parse_shared(event)

        assert row == {"uri": None, "did": DID, "cid": None, "created_at": None}

    @pytest.mark.parametrize("record", ["a string", 42, None, []])
    def test_record_of_the_wrong_type_nulls_created_at(self, record):
        assert parse_shared(make_event(POST_COLLECTION, record))["created_at"] is None

    def test_missing_created_at_is_null(self):
        event = make_event(POST_COLLECTION, post_record())
        del event["commit"]["record"]["createdAt"]

        assert parse_shared(event)["created_at"] is None


class TestValidateNonNullFields:
    def test_true_when_every_required_key_is_present(self):
        row = {"uri": "at://x/y/z", "did": "did:plc:x", "created_at": datetime.now(UTC)}

        assert validate_non_null_fields(row, ("uri", "did", "created_at")) is True

    def test_true_for_no_required_keys(self):
        assert validate_non_null_fields({}, ()) is True

    def test_false_when_a_required_key_is_absent(self):
        assert validate_non_null_fields({"uri": "at://x/y/z"}, ("uri", "did")) is False

    def test_false_when_a_required_key_is_none(self):
        assert validate_non_null_fields({"uri": None, "did": "did:plc:x"}, ("uri", "did")) is False

    def test_ignores_non_required_nulls(self):
        """Optional columns are allowed to be null; only required ones drop a row."""

        row = {"uri": "at://x/y/z", "text": None}

        assert validate_non_null_fields(row, ("uri",)) is True

    def test_empty_string_is_not_null(self):
        assert validate_non_null_fields({"text": ""}, ("text",)) is True

    def test_zero_and_false_are_not_null(self):
        """The check is `is not None`, so falsy values must still pass."""

        assert validate_non_null_fields({"a": 0, "b": False}, ("a", "b")) is True

    def test_timedelta_free_of_ordering_assumptions(self):
        row = {"created_at": datetime.now(UTC) - timedelta(days=1)}

        assert validate_non_null_fields(row, ("created_at",)) is True
