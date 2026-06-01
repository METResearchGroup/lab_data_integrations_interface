"""Tweepy client helpers for the X keyword post fetch experiment."""

from __future__ import annotations

import logging
from typing import Any

import tweepy

from lib.load_env_vars import EnvVarsContainer

logger = logging.getLogger(__name__)

CSV_FIELDNAMES: list[str] = [
    "tweet_id",
    "text",
    "author_id",
    "username",
    "created_at",
    "like_count",
    "retweet_count",
    "reply_count",
    "quote_count",
    "url",
    "keyword",
    "sync_timestamp",
]


def init_x_client() -> tweepy.Client:
    """Build a Tweepy Client using app-only Bearer Token auth."""
    bearer_token = EnvVarsContainer.get_env_var("X_BEARER_TOKEN", required=True)
    return tweepy.Client(bearer_token=bearer_token, wait_on_rate_limit=True)


def _quote_query_term(keyword: str) -> str:
    if any(ch.isspace() for ch in keyword) or any(ch in keyword for ch in ('"', ":", "(", ")")):
        escaped = keyword.replace('"', '\\"')
        return f'"{escaped}"'
    return keyword


def build_query(keyword: str, *, lang: str = "en") -> str:
    """Build a recent-search query for original English posts matching keyword."""
    term = _quote_query_term(keyword)
    return f"{term} lang:{lang} -is:reply -is:retweet -is:quote"


def tweet_to_row(
    tweet: Any,
    *,
    username: str,
    keyword: str,
    sync_timestamp: str,
) -> dict[str, object]:
    """Normalize a Tweepy Tweet to a flat dict matching the CSV schema."""
    metrics = getattr(tweet, "public_metrics", None) or {}
    tweet_id = str(tweet.id)
    return {
        "tweet_id": tweet_id,
        "text": tweet.text or "",
        "author_id": str(tweet.author_id) if tweet.author_id else "",
        "username": username,
        "created_at": str(tweet.created_at) if tweet.created_at else "",
        "like_count": metrics.get("like_count", 0),
        "retweet_count": metrics.get("retweet_count", 0),
        "reply_count": metrics.get("reply_count", 0),
        "quote_count": metrics.get("quote_count", 0),
        "url": f"https://x.com/i/web/status/{tweet_id}",
        "keyword": keyword,
        "sync_timestamp": sync_timestamp,
    }


def _users_by_id(response: Any) -> dict[str, str]:
    users: dict[str, str] = {}
    includes = getattr(response, "includes", None) or {}
    for user in includes.get("users", []) or []:
        users[str(user.id)] = user.username or ""
    return users


def _search_recent_tweets_kwargs(
    query: str,
    max_results: int,
    next_token: str | None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "query": query,
        "max_results": max_results,
        "tweet_fields": ["created_at", "public_metrics", "author_id"],
        "expansions": ["author_id"],
        "user_fields": ["username"],
    }
    if next_token is not None:
        kwargs["next_token"] = next_token
    return kwargs


def _search_recent_tweets(client: tweepy.Client, keyword: str, **kwargs: Any) -> Any:
    try:
        return client.search_recent_tweets(**kwargs)
    except tweepy.TooManyRequests:
        logger.exception("Rate limited while fetching keyword %r", keyword)
        raise


def _append_tweets_from_response(
    response: Any,
    rows: list[dict[str, object]],
    *,
    limit: int,
    keyword: str,
    sync_timestamp: str,
) -> str | None:
    if not response or not response.data:
        return None

    users = _users_by_id(response)
    for tweet in response.data:
        if len(rows) >= limit:
            break
        author_id = str(tweet.author_id) if tweet.author_id else ""
        username = users.get(author_id, "")
        rows.append(
            tweet_to_row(
                tweet,
                username=username,
                keyword=keyword,
                sync_timestamp=sync_timestamp,
            )
        )

    meta = getattr(response, "meta", None) or {}
    return meta.get("next_token")


def fetch_posts_for_keyword(
    client: tweepy.Client,
    keyword: str,
    *,
    limit: int,
    sync_timestamp: str,
) -> list[dict[str, object]]:
    """Fetch up to limit original posts for a keyword via recent search."""
    query = build_query(keyword)
    rows: list[dict[str, object]] = []
    next_token: str | None = None

    while len(rows) < limit:
        max_results = max(10, min(100, limit - len(rows)))
        kwargs = _search_recent_tweets_kwargs(query, max_results, next_token)
        response = _search_recent_tweets(client, keyword, **kwargs)
        next_token = _append_tweets_from_response(
            response,
            rows,
            limit=limit,
            keyword=keyword,
            sync_timestamp=sync_timestamp,
        )
        if not next_token:
            break

    return rows
