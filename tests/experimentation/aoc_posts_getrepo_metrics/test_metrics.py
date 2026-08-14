"""Tests for getRepo-only metric derivation."""

from experimentation.aoc_posts_getrepo_metrics.constants import DELETED_STATUS_UNKNOWN
from experimentation.aoc_posts_getrepo_metrics.metrics import derive_row, derive_rows

POST_URI = "at://did:plc:aoc/app.bsky.feed.post/abc"


def _base_record(**overrides) -> dict:
    record = {
        "$type": "app.bsky.feed.post",
        "text": "hello",
        "createdAt": "2026-01-01T00:00:00.000Z",
        "langs": ["en"],
    }
    record.update(overrides)
    return record


class TestDeriveRow:
    """Tests for derive_row()."""

    def test_derive_row_original_no_media(self) -> None:
        """Marks a non-reply post without media as original."""
        result = derive_row(POST_URI, _base_record())

        assert result["post_type"] == "original"
        assert result["has_image"] is False
        assert result["has_video"] is False
        assert result["deleted"] == DELETED_STATUS_UNKNOWN

    def test_derive_row_reply(self) -> None:
        """Marks posts with a reply block as reply."""
        record = _base_record(
            reply={
                "root": {"uri": "at://did:plc:aoc/app.bsky.feed.post/root", "cid": "cid1"},
                "parent": {"uri": "at://did:plc:aoc/app.bsky.feed.post/parent", "cid": "cid2"},
            }
        )

        result = derive_row(POST_URI, record)

        assert result["post_type"] == "reply"

    def test_derive_row_images_embed(self) -> None:
        """Detects image embeds on the post record."""
        record = _base_record(embed={"$type": "app.bsky.embed.images", "images": []})

        result = derive_row(POST_URI, record)

        assert result["has_image"] is True
        assert result["has_video"] is False

    def test_derive_row_video_embed(self) -> None:
        """Detects video embeds on the post record."""
        record = _base_record(embed={"$type": "app.bsky.embed.video", "video": {}})

        result = derive_row(POST_URI, record)

        assert result["has_video"] is True
        assert result["has_image"] is False

    def test_derive_row_record_with_media_images(self) -> None:
        """Detects images nested under recordWithMedia."""
        record = _base_record(
            embed={
                "$type": "app.bsky.embed.recordWithMedia",
                "record": {"record": {"uri": "at://did:plc:x/app.bsky.feed.post/q"}},
                "media": {"$type": "app.bsky.embed.images", "images": []},
            }
        )

        result = derive_row(POST_URI, record)

        assert result["has_image"] is True

    def test_derive_row_missing_record(self) -> None:
        """Leaves repo-derived fields empty when the record is missing."""
        result = derive_row(POST_URI, None)

        assert result["deleted"] == DELETED_STATUS_UNKNOWN
        assert result["created_at"] is None
        assert result["post_type"] is None
        assert result["has_image"] is None
        assert result["like_count"] is None
        assert result["counts_read_at"] is None

    def test_derive_row_engagement_always_none(self) -> None:
        """Never invents engagement counts from a repo record."""
        result = derive_row(POST_URI, _base_record())

        assert result["like_count"] is None
        assert result["reply_count"] is None
        assert result["repost_count"] is None
        assert result["quote_count"] is None
        assert result["save_count"] is None
        assert result["counts_read_at"] is None


class TestDeriveRows:
    """Tests for derive_rows()."""

    def test_derive_rows_preserves_order(self) -> None:
        """Keeps the caller URI order in the output rows."""
        uri_one = "at://did:plc:aoc/app.bsky.feed.post/1"
        uri_two = "at://did:plc:aoc/app.bsky.feed.post/2"
        posts_by_uri = {
            uri_one: _base_record(text="one"),
            uri_two: _base_record(text="two"),
        }

        result = derive_rows([uri_two, uri_one], posts_by_uri)

        assert [row["post_uri"] for row in result] == [uri_two, uri_one]
