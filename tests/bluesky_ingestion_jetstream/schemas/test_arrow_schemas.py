"""Tests for the PyArrow table schemas."""

import pyarrow as pa
import pytest

from bluesky_ingestion_jetstream.constants import FOLLOWS, LIKES, POSTS, RECORD_TYPES, REPOSTS
from bluesky_ingestion_jetstream.schemas.arrow_schemas import (
    FOLLOW_SCHEMA,
    LIKE_SCHEMA,
    POST_SCHEMA,
    RECORD_TYPE_TO_SCHEMA,
    REPOST_SCHEMA,
)

COMMON_COLUMNS = {"uri", "did", "cid", "created_at"}


class TestRecordTypeToSchema:
    def test_covers_every_record_type(self):
        assert set(RECORD_TYPE_TO_SCHEMA) == set(RECORD_TYPES)

    def test_maps_each_type_to_its_schema(self):
        assert RECORD_TYPE_TO_SCHEMA == {
            POSTS: POST_SCHEMA,
            LIKES: LIKE_SCHEMA,
            REPOSTS: REPOST_SCHEMA,
            FOLLOWS: FOLLOW_SCHEMA,
        }


class TestCommonColumns:
    @pytest.mark.parametrize("record_type", RECORD_TYPES)
    def test_every_table_has_them(self, record_type):
        assert COMMON_COLUMNS.issubset(set(RECORD_TYPE_TO_SCHEMA[record_type].names))

    @pytest.mark.parametrize("record_type", RECORD_TYPES)
    def test_created_at_is_microsecond_utc(self, record_type):
        schema = RECORD_TYPE_TO_SCHEMA[record_type]

        assert schema.field("created_at").type == pa.timestamp("us", tz="UTC")

    @pytest.mark.parametrize("record_type", RECORD_TYPES)
    def test_identifier_columns_are_strings(self, record_type):
        schema = RECORD_TYPE_TO_SCHEMA[record_type]

        for column in ("uri", "did", "cid"):
            assert schema.field(column).type == pa.string()

    @pytest.mark.parametrize("record_type", RECORD_TYPES)
    def test_every_column_is_nullable(self, record_type):
        """One odd record must not fail an entire flush."""

        schema = RECORD_TYPE_TO_SCHEMA[record_type]

        assert all(schema.field(name).nullable for name in schema.names)


class TestPostSchema:
    def test_has_exactly_its_columns(self):
        assert set(POST_SCHEMA.names) == COMMON_COLUMNS | {
            "text",
            "langs",
            "reply_root_uri",
            "reply_parent_uri",
            "embed_type",
        }

    def test_langs_is_a_list_of_strings(self):
        assert POST_SCHEMA.field("langs").type == pa.list_(pa.string())


class TestInteractionSchemas:
    def test_likes_have_exactly_their_columns(self):
        assert set(LIKE_SCHEMA.names) == COMMON_COLUMNS | {"subject_uri", "subject_cid"}

    def test_reposts_alias_likes(self):
        """Identical record shapes, so the schema is shared rather than duplicated."""

        assert REPOST_SCHEMA is LIKE_SCHEMA


class TestFollowSchema:
    def test_has_exactly_its_columns(self):
        assert set(FOLLOW_SCHEMA.names) == COMMON_COLUMNS | {"subject_did"}

    def test_subject_did_is_a_string(self):
        """Both ends of the follow edge are DIDs, never handles."""

        assert FOLLOW_SCHEMA.field("subject_did").type == pa.string()


class TestSchemasMatchParsedRows:
    @pytest.mark.parametrize("record_type", RECORD_TYPES)
    def test_parsed_rows_have_exactly_the_schema_columns(self, record_type, rows_factory):
        """A drifted column would silently null out or fail the Parquet write."""

        row = rows_factory(record_type, 1)[0]

        assert set(row) == set(RECORD_TYPE_TO_SCHEMA[record_type].names)
