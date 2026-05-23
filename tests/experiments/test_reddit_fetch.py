import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

EXPERIMENT_DIR = Path(__file__).resolve().parents[2] / "experiments" / "reddit_fetch_data_2026_05_23"
sys.path.insert(0, str(EXPERIMENT_DIR))

from reddit_client import (  # noqa: E402
    CSV_FIELDNAMES,
    fetch_subreddit_posts,
    submission_to_row,
)
from main import write_metadata  # noqa: E402

SYNC_TIMESTAMP = "2026_05_23-14:30:00"


def _make_submission(**overrides: object) -> MagicMock:
    post = MagicMock()
    post.id = "abc123"
    post.name = "t3_abc123"
    post.subreddit.display_name = "Conservative"
    post.title = "Test title"
    post.selftext = "Test body"
    post.author = MagicMock(__str__=MagicMock(return_value="test_user"))
    post.score = 42
    post.upvote_ratio = 0.87
    post.num_comments = 5
    post.created_utc = 1_700_000_000.0
    post.permalink = "/r/Conservative/comments/abc123/test_title/"
    post.url = "https://reddit.com/r/Conservative/comments/abc123/test_title/"
    post.is_self = True
    for key, value in overrides.items():
        setattr(post, key, value)
    return post


def test_submission_to_row_maps_all_fields():
    post = _make_submission()
    row = submission_to_row(post, SYNC_TIMESTAMP)

    assert list(row.keys()) == CSV_FIELDNAMES
    assert row["reddit_id"] == "abc123"
    assert row["reddit_fullname"] == "t3_abc123"
    assert row["subreddit"] == "Conservative"
    assert row["title"] == "Test title"
    assert row["selftext"] == "Test body"
    assert row["author"] == "test_user"
    assert row["score"] == 42
    assert row["upvote_ratio"] == 0.87
    assert row["num_comments"] == 5
    assert row["created_utc"] == "2023-11-14T22:13:20+00:00"
    assert row["permalink"] == "/r/Conservative/comments/abc123/test_title/"
    assert row["url"] == "https://reddit.com/r/Conservative/comments/abc123/test_title/"
    assert row["is_self"] is True
    assert row["sync_timestamp"] == SYNC_TIMESTAMP


def test_submission_to_row_deleted_author():
    post = _make_submission(author=None)
    row = submission_to_row(post, SYNC_TIMESTAMP)
    assert row["author"] == "[deleted]"


def test_fetch_subreddit_posts_limit():
    reddit = MagicMock()
    mock_posts = [_make_submission(id=f"id{i}", name=f"t3_id{i}") for i in range(10)]
    reddit.subreddit.return_value.hot.return_value = mock_posts

    rows = fetch_subreddit_posts(reddit, "Conservative", limit=10, sync_timestamp=SYNC_TIMESTAMP)

    reddit.subreddit.assert_called_once_with("Conservative")
    reddit.subreddit.return_value.hot.assert_called_once_with(limit=10)
    assert len(rows) == 10
    assert all(row["sync_timestamp"] == SYNC_TIMESTAMP for row in rows)


def test_write_metadata_structure(tmp_path: Path):
    counts = {
        "conservative": 10,
        "republican": 10,
        "askconservatives": 10,
        "politics": 10,
        "liberal": 10,
        "democrats": 10,
    }
    files = {key: f"{key}.csv" for key in counts}

    metadata = write_metadata(
        output_dir=tmp_path,
        sync_timestamp=SYNC_TIMESTAMP,
        subreddits=[
            "Conservative",
            "Republican",
            "AskConservatives",
            "politics",
            "liberal",
            "democrats",
        ],
        posts_per_subreddit=10,
        counts=counts,
        files=files,
    )

    assert metadata["sync_timestamp"] == SYNC_TIMESTAMP
    assert metadata["posts_per_subreddit"] == 10
    assert metadata["total_posts"] == 60
    assert metadata["counts"] == counts
    assert metadata["files"] == files

    with open(tmp_path / "metadata.json", encoding="utf-8") as f:
        written = json.load(f)
    assert written == metadata
