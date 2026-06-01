from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from experiments.x_fetch_data_2026_06_01.x_client import (
    CSV_FIELDNAMES,
    build_query,
    fetch_posts_for_keyword,
    tweet_to_row,
)


def test_build_query_quotes_multiword() -> None:
    assert (
        build_query("gun control")
        == '"gun control" lang:en -is:reply -is:retweet -is:quote'
    )


def test_build_query_single_word() -> None:
    assert build_query("DACA") == "DACA lang:en -is:reply -is:retweet -is:quote"


def test_tweet_to_row_maps_fields() -> None:
    tweet = SimpleNamespace(
        id=1234567890,
        text="Gun control debate continues...",
        author_id=987654321,
        created_at="2026-05-30T14:22:01.000Z",
        public_metrics={
            "like_count": 42,
            "retweet_count": 5,
            "reply_count": 3,
            "quote_count": 0,
        },
    )
    row = tweet_to_row(
        tweet,
        username="example_user",
        keyword="gun control",
        sync_timestamp="2026_06_01-15:30:00",
    )
    assert list(row.keys()) == CSV_FIELDNAMES
    assert row["tweet_id"] == "1234567890"
    assert row["username"] == "example_user"
    assert row["url"] == "https://x.com/i/web/status/1234567890"
    assert row["like_count"] == 42


def _make_tweet(tweet_id: int, author_id: int = 100) -> SimpleNamespace:
    return SimpleNamespace(
        id=tweet_id,
        text=f"post {tweet_id}",
        author_id=author_id,
        created_at="2026-05-30T14:22:01.000Z",
        public_metrics={
            "like_count": 1,
            "retweet_count": 0,
            "reply_count": 0,
            "quote_count": 0,
        },
    )


def _make_user(user_id: int, username: str) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, username=username)


def test_fetch_posts_for_keyword_respects_limit() -> None:
    limit = 15
    page1_tweets = [_make_tweet(i) for i in range(10)]
    page2_tweets = [_make_tweet(i) for i in range(10, 20)]
    page1_users = [_make_user(100, "user100")]
    page2_users = [_make_user(100, "user100")]

    page1 = SimpleNamespace(
        data=page1_tweets,
        includes={"users": page1_users},
        meta={"next_token": "token-2"},
    )
    page2 = SimpleNamespace(
        data=page2_tweets,
        includes={"users": page2_users},
        meta={},
    )

    client = MagicMock()
    client.search_recent_tweets.side_effect = [page1, page2]

    rows = fetch_posts_for_keyword(
        client,
        "gun control",
        limit=limit,
        sync_timestamp="2026_06_01-15:30:00",
    )

    assert len(rows) == limit
    assert client.search_recent_tweets.call_count == 2


def test_fetch_posts_for_keyword_stops_on_empty() -> None:
    client = MagicMock()
    client.search_recent_tweets.return_value = SimpleNamespace(data=None, includes={}, meta={})

    rows = fetch_posts_for_keyword(
        client,
        "DACA",
        limit=10,
        sync_timestamp="2026_06_01-15:30:00",
    )

    assert rows == []
    assert client.search_recent_tweets.call_count == 1
