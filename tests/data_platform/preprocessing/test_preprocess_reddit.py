from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from data_platform.preprocessing import preprocess_reddit
from data_platform.preprocessing.validators import reddit_validators
from data_platform.utils.storage import RedditStorageManager
from tests.data_platform.constants import VALID_REDDIT_DATASET_ID
from tests.data_platform.ingestion.reddit_conftest import mock_comment_row


def _valid_body() -> str:
    return "This is a clear English comment about policy and governance without links or mentions."


def _comment_row(**overrides: Any) -> dict[str, Any]:
    comment_fullname = overrides.pop("comment_fullname", "t1_valid_comment")
    subreddit = overrides.pop("subreddit", "politics")
    row = mock_comment_row(comment_fullname, subreddit=subreddit)
    row["body"] = _valid_body()
    row["author"] = "regular_user"
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (_valid_body(), True),
        ("[removed]", False),
        ("[deleted]", False),
        ("[removed by reddit]", False),
        ("[unavailable]", False),
        ("Check out u/example_user for more context on this issue.", False),
        ("See r/politics for the original thread discussion.", False),
        ("Read [this article](https://example.com/story) for details.", False),
        ("![image](https://example.com/pic.png)", False),
        ("Visit https://example.com for more information today.", False),
        ("Watch this on youtube for the full segment.", False),
        ("Hosted on i.redd.it with a screenshot attached.", False),
    ],
)
def test_reddit_text_validators(body: str, expected: bool) -> None:
    row = _comment_row(body=body)
    assert preprocess_reddit.passes_all_validators(row["body"]) is expected


@pytest.mark.parametrize(
    ("author", "expected"),
    [
        ("regular_user", True),
        ("AutoModerator", False),
        ("automoderator", False),
    ],
)
def test_reddit_row_validators(author: str, expected: bool) -> None:
    assert preprocess_reddit.passes_row_validators(author) is expected


def test_filter_comments_drops_invalid_rows() -> None:
    comments = pd.DataFrame(
        [
            _comment_row(comment_fullname="t1_keep"),
            _comment_row(
                comment_fullname="t1_drop_removed",
                body="[removed]",
            ),
            _comment_row(
                comment_fullname="t1_drop_mod",
                author="AutoModerator",
            ),
        ]
    )
    filtered = preprocess_reddit.filter_comments(comments)
    assert len(filtered) == 1
    assert filtered.iloc[0]["comment_fullname"] == "t1_keep"


def test_preprocess_records_writes_output(data_root) -> None:
    dataset_id = VALID_REDDIT_DATASET_ID
    raw_storage = RedditStorageManager("raw", dataset_id)
    run_dir = raw_storage.create_new_run_dir("2026_05_31-10:00:00")
    raw_storage.write_records(
        [
            _comment_row(comment_fullname="t1_keep"),
            _comment_row(
                comment_fullname="t1_drop",
                body="[deleted]",
            ),
        ],
        run_dir,
    )
    raw_storage.write_run_metadata(
        run_dir,
        {
            "sync_status": "completed",
            "row_count": 2,
        },
    )

    output_dir = preprocess_reddit.preprocess_records(dataset_id)

    preprocessed_storage = RedditStorageManager("preprocessed", dataset_id)
    output = preprocessed_storage.load_records(output_dir)
    metadata = preprocessed_storage.load_run_metadata(output_dir)

    assert len(output) == 1
    assert output.iloc[0]["comment_fullname"] == "t1_keep"
    assert metadata["row_counts"]["input"] == 2
    assert metadata["row_counts"]["output"] == 1
    assert metadata["files"]["comments"] == "comments.csv"


def test_individual_reddit_validator_functions() -> None:
    assert reddit_validators.check_if_body_not_removed(_valid_body())
    assert not reddit_validators.check_if_body_not_removed("[removed]")
    assert reddit_validators.check_if_no_reddit_mentions(_valid_body())
    assert not reddit_validators.check_if_no_reddit_mentions("ping u/someone")
    assert reddit_validators.check_if_no_markdown_links(_valid_body())
    assert not reddit_validators.check_if_no_markdown_links("[link](https://x.com)")
    assert reddit_validators.check_if_no_direct_urls(_valid_body())
    assert not reddit_validators.check_if_no_direct_urls("see https://example.com")
    assert reddit_validators.check_if_no_media_hosts(_valid_body())
    assert not reddit_validators.check_if_no_media_hosts("clip on youtu.be please")
    assert reddit_validators.check_if_not_automoderator("user")
    assert not reddit_validators.check_if_not_automoderator("AutoModerator")
