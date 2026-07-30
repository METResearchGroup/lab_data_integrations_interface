"""Tests for the shared commit columns and the defensive access helpers."""

from datetime import UTC, datetime, timedelta

import pytest

from bluesky_ingestion_jetstream.constants import (
    COMMON_REQUIRED_KEYS,
    EARLIEST_VALID_CREATED_AT,
    MAX_CREATED_AT_SKEW,
)
from bluesky_ingestion_jetstream.event_parsing.shared import (
    as_dict,
    as_str,
    as_str_list,
    parse_created_at,
    parse_ingested_at,
    parse_shared,
    validate_non_null_fields,
)
from tests.bluesky_ingestion_jetstream.conftest import (
    CID,
    CREATED_AT,
    CREATED_AT_STR,
    DID,
    INGESTED_AT,
    POST_COLLECTION,
    REV,
    RKEY,
    TIME_US,
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


class TestParseIngestedAt:
    def test_converts_microseconds_to_utc(self):
        assert parse_ingested_at(TIME_US) == INGESTED_AT

    def test_microseconds_are_preserved(self):
        """Integer arithmetic throughout, so the sub-second part cannot be rounded off."""

        parsed = parse_ingested_at(TIME_US)

        assert parsed is not None
        assert parsed.microsecond == TIME_US % 1_000_000

    def test_result_is_utc(self):
        parsed = parse_ingested_at(TIME_US)

        assert parsed is not None
        assert parsed.tzinfo == UTC

    def test_epoch_is_zero(self):
        assert parse_ingested_at(0) == datetime(1970, 1, 1, tzinfo=UTC)

    @pytest.mark.parametrize("value", ["1784533137411372", None, [], {}, 1.5])
    def test_non_integers_become_none(self, value):
        assert parse_ingested_at(value) is None

    @pytest.mark.parametrize("value", [True, False])
    def test_bools_become_none(self, value):
        """`isinstance(True, int)` is True, so bools need excluding explicitly."""

        assert parse_ingested_at(value) is None

    def test_out_of_range_becomes_none(self):
        """Client junk must null the column, not raise out of the parse path."""

        assert parse_ingested_at(10**20) is None


class TestCreatedAtRange:
    """`created_at` is client-supplied and is the Iceberg partition key.

    An out-of-range value is nulled by `parse_shared`, which makes the row fail
    the required-key check and be dropped. These assert on `parse_shared` rather
    than on `is_created_at_in_range` alone, because the nulling is the part that
    actually keeps junk out of the table.
    """

    def test_a_plausible_timestamp_survives(self, post_event):
        assert parse_shared(post_event)["created_at"] == CREATED_AT

    @pytest.mark.parametrize("createdAt", ["1970-01-01T00:00:00Z", "2021-12-31T23:59:59Z"])
    def test_timestamps_before_the_floor_are_nulled(self, post_event, createdAt):
        post_event["commit"]["record"]["createdAt"] = createdAt

        assert parse_shared(post_event)["created_at"] is None

    def test_the_floor_itself_is_accepted(self, post_event):
        """A boundary that rejected its own limit would be off by one day of data."""

        post_event["commit"]["record"]["createdAt"] = EARLIEST_VALID_CREATED_AT.isoformat()

        assert parse_shared(post_event)["created_at"] == EARLIEST_VALID_CREATED_AT

    def test_timestamps_far_ahead_of_the_broker_are_nulled(self, post_event):
        far_future = INGESTED_AT + MAX_CREATED_AT_SKEW + timedelta(seconds=1)
        post_event["commit"]["record"]["createdAt"] = far_future.isoformat()

        assert parse_shared(post_event)["created_at"] is None

    def test_a_clock_within_the_skew_allowance_is_kept(self, post_event):
        """A misconfigured device clock is not junk, and dropping it loses real posts."""

        ahead = INGESTED_AT + MAX_CREATED_AT_SKEW - timedelta(seconds=1)
        post_event["commit"]["record"]["createdAt"] = ahead.isoformat()

        assert parse_shared(post_event)["created_at"] == ahead

    def test_the_ceiling_follows_the_broker_clock_not_the_wall_clock(self, post_event):
        """Replay redelivers old events to a much later wall clock; they must survive."""

        post_event["time_us"] = TIME_US
        post_event["commit"]["record"]["createdAt"] = CREATED_AT.isoformat()

        assert parse_shared(post_event)["created_at"] == CREATED_AT

    def test_a_null_ingested_at_leaves_only_the_floor(self, post_event):
        """With no broker clock the ceiling cannot be applied -- the row dies anyway."""

        del post_event["time_us"]
        post_event["commit"]["record"]["createdAt"] = "2099-01-01T00:00:00Z"
        row = parse_shared(post_event)

        assert row["created_at"] == datetime(2099, 1, 1, tzinfo=UTC)
        assert not validate_non_null_fields(row, ["ingested_at"])

    def test_an_out_of_range_row_is_dropped_by_the_required_key_check(self, post_event):
        post_event["commit"]["record"]["createdAt"] = "1999-01-01T00:00:00Z"
        row = parse_shared(post_event)

        assert not validate_non_null_fields(row, COMMON_REQUIRED_KEYS)


class TestParseShared:
    def test_extracts_every_common_column(self, post_event):
        row = parse_shared(post_event)

        assert row == {
            "uri": f"at://{DID}/{POST_COLLECTION}/{RKEY}",
            "did": DID,
            "cid": CID,
            "rev": REV,
            "created_at": CREATED_AT,
            "ingested_at": INGESTED_AT,
        }

    def test_rev_comes_from_the_commit(self, post_event):
        assert parse_shared(post_event)["rev"] == REV

    def test_missing_rev_is_null(self, post_event):
        del post_event["commit"]["rev"]

        assert parse_shared(post_event)["rev"] is None

    def test_the_two_clocks_are_read_from_different_places(self, post_event):
        """`created_at` is the client's, `ingested_at` the broker's. Never the same field."""

        row = parse_shared(post_event)

        assert row["created_at"] == CREATED_AT
        assert row["ingested_at"] == INGESTED_AT
        assert row["created_at"] != row["ingested_at"]

    def test_missing_time_us_nulls_ingested_at(self, post_event):
        del post_event["time_us"]

        assert parse_shared(post_event)["ingested_at"] is None

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

    def test_missing_commit_leaves_only_the_envelope_columns(self):
        """`did` and `ingested_at` live on the envelope, so they outlive a bad commit."""

        event = make_event(POST_COLLECTION, post_record(), drop_commit=True)
        row = parse_shared(event)

        assert row == {
            "uri": None,
            "did": DID,
            "cid": None,
            "rev": None,
            "created_at": None,
            "ingested_at": INGESTED_AT,
        }

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
