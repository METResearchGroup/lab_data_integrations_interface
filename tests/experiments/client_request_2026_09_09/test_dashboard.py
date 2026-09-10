"""Tests for dashboard data serialization and bsky.app URL construction."""

from datetime import datetime
from pathlib import Path

from experiments.client_request_2026_09_09.dashboard.prepare_data import (
    serialize_row,
)
from experiments.client_request_2026_09_09.urls import bsky_post_url

DASHBOARD_DIR = Path("experiments/client_request_2026_09_09/dashboard")


class TestBskyPostUrl:
    """Tests for bsky_post_url()."""

    def test_builds_profile_post_url(self):
        """A standard AT-URI post maps to bsky.app."""
        # Arrange
        uri = "at://did:plc:abc/app.bsky.feed.post/xyz"

        # Act
        result = bsky_post_url(uri)

        # Assert
        assert result == "https://bsky.app/profile/did:plc:abc/post/xyz"

    def test_rejects_non_post_collection(self):
        """Likes and other collections do not get a post URL."""
        # Arrange
        uri = "at://did:plc:abc/app.bsky.feed.like/xyz"

        # Act
        result = bsky_post_url(uri)

        # Assert
        assert result is None

    def test_rejects_missing_uri(self):
        """A missing AT-URI does not get a post URL."""
        # Arrange / Act
        result = bsky_post_url(None)

        # Assert
        assert result is None


class TestSerializeRow:
    """Tests for serialize_row()."""

    def test_includes_fields_and_iso_timestamp(self):
        """Explorer JSON keeps the Parquet fields plus a bsky URL."""
        # Arrange
        row = {
            "uri": "at://did:plc:abc/app.bsky.feed.post/xyz",
            "did": "did:plc:abc",
            "text": "roy cooper news",
            "created_at": datetime(2026, 8, 15, 12, 0, 0),
            "matched_candidate": "cooper",
            "matched_name_string": "roy cooper",
        }

        # Act
        result = serialize_row(row)

        # Assert
        assert result["uri"] == row["uri"]
        assert result["did"] == "did:plc:abc"
        assert result["text"] == "roy cooper news"
        assert result["created_at"] == "2026-08-15T12:00:00"
        assert result["matched_candidate"] == "cooper"
        assert result["matched_name_string"] == "roy cooper"
        assert result["bsky_url"] == "https://bsky.app/profile/did:plc:abc/post/xyz"


    def test_prefers_parquet_url_when_present(self):
        """serialize_row uses a url column when the Parquet row already has one."""
        # Arrange
        row = {
            "uri": "at://did:plc:abc/app.bsky.feed.post/xyz",
            "did": "did:plc:abc",
            "text": "roy cooper news",
            "created_at": datetime(2026, 8, 15, 12, 0, 0),
            "matched_candidate": "cooper",
            "matched_name_string": "roy cooper",
            "url": "https://bsky.app/profile/did:plc:abc/post/xyz",
        }

        # Act
        result = serialize_row(row)

        # Assert
        assert result["bsky_url"] == row["url"]


class TestDashboardConfig:
    """Tests for the committed explorer config."""

    def test_urls_are_relative_gzip_paths(self):
        """config.js must not embed AWS credentials or presigned query strings."""
        # Arrange
        text = (DASHBOARD_DIR / "config.js").read_text(encoding="utf-8")

        # Act / Assert
        assert "X-Amz-" not in text
        assert "AWS_ACCESS_KEY_ID" not in text
        assert '"url": "data/el_sayed.json.gz"' in text
        assert '"url": "data/cooper.json.gz"' in text
