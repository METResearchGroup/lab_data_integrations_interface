"""Tweepy client helpers for Twitter/X recent-search ingestion."""

from __future__ import annotations

import logging
from typing import Any

import tweepy

from data_platform.ingestion.twitter_retry import retry_twitter_request

logger = logging.getLogger(__name__)

_EXCLUDE_CLAUSES: dict[str, str] = {
    "reply": "-is:reply",
    "retweet": "-is:retweet",
    "quote": "-is:quote",
}


def _quote_query_term(keyword: str) -> str:
    if any(ch.isspace() for ch in keyword) or any(ch in keyword for ch in ('"', ":", "(", ")")):
        escaped = keyword.replace('"', '\\"')
        return f'"{escaped}"'
    return keyword


def build_query(
    keyword: str,
    *,
    lang: str = "en",
    exclude: list[str] | None = None,
) -> str:
    """Build a recent-search query for original posts matching keyword."""
    term = _quote_query_term(keyword)
    parts = [term, f"lang:{lang}"]
    for item in exclude or ("reply", "retweet", "quote"):
        clause = _EXCLUDE_CLAUSES.get(item)
        if clause:
            parts.append(clause)
    return " ".join(parts)


def tweet_to_row(
    tweet: Any,
    *,
    username: str,
    keyword: str,
    sync_timestamp: str,
) -> dict[str, object]:
    """Normalize a Tweepy Tweet to a flat dict matching the raw CSV schema."""
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


@retry_twitter_request()
def _search_recent_tweets(client: tweepy.Client, **kwargs: Any) -> Any:
    return client.search_recent_tweets(**kwargs)


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
    lang: str,
    exclude: list[str],
    sync_timestamp: str,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Fetch up to limit original posts for a keyword via recent search."""
    query = build_query(keyword, lang=lang, exclude=exclude)
    rows: list[dict[str, object]] = []
    next_token: str | None = None
    pages_fetched = 0
    next_token_seen = False

    while len(rows) < limit:
        max_results = max(10, min(100, limit - len(rows)))
        kwargs = _search_recent_tweets_kwargs(query, max_results, next_token)
        response = _search_recent_tweets(client, **kwargs)
        pages_fetched += 1
        prev_token = next_token
        next_token = _append_tweets_from_response(
            response,
            rows,
            limit=limit,
            keyword=keyword,
            sync_timestamp=sync_timestamp,
        )
        if next_token and next_token != prev_token:
            next_token_seen = True
        if not next_token:
            break

    rows = rows[:limit]
    stats: dict[str, object] = {
        "pages_fetched": pages_fetched,
        "rows_collected": len(rows),
        "next_token_seen": next_token_seen,
    }
    return rows, stats
