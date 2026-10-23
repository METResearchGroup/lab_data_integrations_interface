"""Tests for Jetstream event parsing and the createdAt fallback rule."""

from __future__ import annotations

from datetime import UTC, datetime

from experimentation.iceberg import constants, schemas

# 2026-07-22T12:00:00Z
INGEST_US = 1_784_721_600_000_000
INGEST_DT = datetime.fromtimestamp(INGEST_US / 1_000_000, tz=UTC)


def _event(collection: str, record: dict | None, operation: str = "create") -> dict:
    commit = {
        "rev": "3l3qo2vutsw2b",
        "operation": operation,
        "collection": collection,
        "rkey": "3l3qo2vuowo2b",
        "cid": "bafyreiabc",
    }
    if record is not None:
        commit["record"] = record
    return {"did": "did:plc:alice", "time_us": INGEST_US, "kind": "commit", "commit": commit}


class TestRouting:
    def test_post(self):
        parsed = schemas.parse_event(
            _event("app.bsky.feed.post", {"text": "hello", "createdAt": "2026-07-22T12:00:00.000Z"})
        )
        assert parsed is not None
        record_type, row = parsed
        assert record_type == "posts"
        assert row["text"] == "hello"
        assert row["text_length"] == 5
        assert row["uri"] == "at://did:plc:alice/app.bsky.feed.post/3l3qo2vuowo2b"

    def test_like_extracts_subject_strongref(self):
        record = {
            "createdAt": "2026-07-22T12:00:00Z",
            "subject": {"uri": "at://did:plc:bob/app.bsky.feed.post/xyz", "cid": "bafy1"},
        }
        parsed = schemas.parse_event(_event("app.bsky.feed.like", record))
        assert parsed is not None
        record_type, row = parsed
        assert record_type == "likes"
        assert row["subject_uri"] == "at://did:plc:bob/app.bsky.feed.post/xyz"
        assert row["subject_cid"] == "bafy1"

    def test_follow_subject_is_a_plain_did(self):
        parsed = schemas.parse_event(
            _event(
                "app.bsky.graph.follow",
                {"createdAt": "2026-07-22T12:00:00Z", "subject": "did:plc:bob"},
            )
        )
        assert parsed is not None
        record_type, row = parsed
        assert record_type == "follows"
        assert row["subject_did"] == "did:plc:bob"

    def test_repost(self):
        record = {"createdAt": "2026-07-22T12:00:00Z", "subject": {"uri": "at://x", "cid": "c"}}
        parsed = schemas.parse_event(_event("app.bsky.feed.repost", record))
        assert parsed is not None
        assert parsed[0] == "reposts"

    def test_untracked_collection_is_dropped(self):
        assert (
            schemas.parse_event(
                _event("app.bsky.actor.profile", {"createdAt": "2026-07-22T12:00:00Z"})
            )
            is None
        )

    def test_non_commit_kinds_are_dropped(self):
        assert schemas.parse_event({"kind": "identity", "did": "did:plc:alice"}) is None

    def test_missing_commit_is_dropped(self):
        assert schemas.parse_event({"kind": "commit", "did": "did:plc:alice"}) is None

    def test_missing_rkey_is_dropped(self):
        event = _event("app.bsky.feed.post", {"createdAt": "2026-07-22T12:00:00Z"})
        event["commit"]["rkey"] = ""
        assert schemas.parse_event(event) is None


class TestCreatedAtFallback:
    def test_valid_timestamp_is_kept(self):
        parsed = schemas.parse_event(
            _event("app.bsky.feed.post", {"createdAt": "2026-07-22T11:59:00Z"})
        )
        assert parsed is not None
        _, row = parsed
        assert row["created_at_fallback"] is False
        assert row["created_at"] == datetime(2026, 7, 22, 11, 59, tzinfo=UTC)

    def test_malformed_timestamp_falls_back(self):
        parsed = schemas.parse_event(_event("app.bsky.feed.post", {"createdAt": "not-a-date"}))
        assert parsed is not None
        _, row = parsed
        assert row["created_at_fallback"] is True
        assert row["created_at"] == INGEST_DT

    def test_far_future_timestamp_falls_back(self):
        """A year-2100 createdAt would otherwise open a junk daily partition."""
        parsed = schemas.parse_event(
            _event("app.bsky.feed.post", {"createdAt": "2100-01-01T00:00:00Z"})
        )
        assert parsed is not None
        _, row = parsed
        assert row["created_at_fallback"] is True
        assert row["created_at"] == INGEST_DT

    def test_epoch_zero_falls_back(self):
        parsed = schemas.parse_event(
            _event("app.bsky.feed.post", {"createdAt": "1970-01-01T00:00:00Z"})
        )
        assert parsed is not None
        assert parsed[1]["created_at_fallback"] is True

    def test_skew_inside_the_window_is_kept(self):
        """Genuinely backdated-but-plausible records must not be rewritten."""
        parsed = schemas.parse_event(
            _event("app.bsky.feed.post", {"createdAt": "2026-07-22T00:00:01Z"})
        )
        assert parsed is not None
        assert parsed[1]["created_at_fallback"] is False

    def test_missing_created_at_falls_back(self):
        parsed = schemas.parse_event(_event("app.bsky.feed.post", {"text": "no timestamp"}))
        assert parsed is not None
        assert parsed[1]["created_at_fallback"] is True

    def test_delete_has_no_record_body(self):
        parsed = schemas.parse_event(_event("app.bsky.feed.post", None, operation="delete"))
        assert parsed is not None
        _, row = parsed
        assert row["operation"] == "delete"
        assert row["created_at_fallback"] is True
        assert row["text"] is None

    def test_naive_timestamp_is_treated_as_utc(self):
        parsed = schemas.parse_event(
            _event("app.bsky.feed.post", {"createdAt": "2026-07-22T11:59:00"})
        )
        assert parsed is not None
        assert parsed[1]["created_at_fallback"] is False


class TestNestedFields:
    def test_reply_refs(self):
        record = {
            "createdAt": "2026-07-22T12:00:00Z",
            "text": "reply",
            "reply": {"root": {"uri": "at://root"}, "parent": {"uri": "at://parent"}},
        }
        parsed = schemas.parse_event(_event("app.bsky.feed.post", record))
        assert parsed is not None
        _, row = parsed
        assert row["reply_root_uri"] == "at://root"
        assert row["reply_parent_uri"] == "at://parent"

    def test_malformed_nested_values_do_not_raise(self):
        record = {
            "createdAt": "2026-07-22T12:00:00Z",
            "reply": "garbage",
            "embed": 42,
            "langs": "en",
        }
        parsed = schemas.parse_event(_event("app.bsky.feed.post", record))
        assert parsed is not None
        _, row = parsed
        assert row["reply_root_uri"] is None
        assert row["embed_type"] is None
        assert row["langs"] is None

    def test_embed_type(self):
        record = {"createdAt": "2026-07-22T12:00:00Z", "embed": {"$type": "app.bsky.embed.images"}}
        parsed = schemas.parse_event(_event("app.bsky.feed.post", record))
        assert parsed is not None
        assert parsed[1]["embed_type"] == "app.bsky.embed.images"


class TestFieldIds:
    """Guards against a silent-NULL bug that already happened once.

    ``Catalog.create_table`` renumbers schema fields contiguously from 1, and
    Iceberg resolves columns by field id rather than name. Declaring
    non-contiguous ids means writes stamp the declared ids into Parquet while
    the table metadata records the renumbered ones -- reads then find nothing
    and return NULL for every affected column, with no error anywhere.
    """

    def test_top_level_ids_are_contiguous_from_one(self):
        for record_type, schema in schemas.SCHEMAS.items():
            ids = [field.field_id for field in schema.fields]
            assert ids == list(range(1, len(ids) + 1)), (
                f"{record_type} declares {ids}; create_table would assign "
                f"{list(range(1, len(ids) + 1))}, and the mismatch reads back as NULL"
            )

    def test_nested_element_ids_follow_every_top_level_field(self):
        """Nested ids are assigned after all top-level fields, not next to their parent."""
        posts = schemas.SCHEMAS["posts"]
        langs = posts.find_field("langs")
        top_level_count = len(posts.fields)
        assert langs.field_type.element_id == top_level_count + 1

    def test_common_header_is_identical_across_tables(self):
        header = [(f.field_id, f.name) for f in schemas.SCHEMAS["posts"].fields[:10]]
        for record_type, schema in schemas.SCHEMAS.items():
            assert [(f.field_id, f.name) for f in schema.fields[:10]] == header, record_type


class TestSchemaShape:
    def test_every_record_type_has_a_schema(self):
        assert set(schemas.SCHEMAS) == set(constants.RECORD_TYPES)

    def test_partition_source_is_created_at(self):
        for record_type, schema in schemas.SCHEMAS.items():
            field = schema.find_field(schemas.CREATED_AT_FIELD_ID)
            assert field.name == "created_at", record_type

    def test_parsed_rows_only_use_declared_columns(self):
        """A key not in the schema would be silently dropped at Arrow conversion."""
        samples = {
            "app.bsky.feed.post": {"createdAt": "2026-07-22T12:00:00Z", "text": "x"},
            "app.bsky.feed.like": {
                "createdAt": "2026-07-22T12:00:00Z",
                "subject": {"uri": "u", "cid": "c"},
            },
            "app.bsky.feed.repost": {
                "createdAt": "2026-07-22T12:00:00Z",
                "subject": {"uri": "u", "cid": "c"},
            },
            "app.bsky.graph.follow": {
                "createdAt": "2026-07-22T12:00:00Z",
                "subject": "did:plc:bob",
            },
        }
        for collection, record in samples.items():
            parsed = schemas.parse_event(_event(collection, record))
            assert parsed is not None
            record_type, row = parsed
            declared = {field.name for field in schemas.SCHEMAS[record_type].fields}
            assert set(row) <= declared, f"{record_type}: {set(row) - declared}"
