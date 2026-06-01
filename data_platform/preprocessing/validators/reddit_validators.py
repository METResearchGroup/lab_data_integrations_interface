"""Reddit-specific preprocessing validators for comment body and author fields."""

from __future__ import annotations

import re

REMOVED_BODY_SENTINELS = frozenset(
    {
        "[removed]",
        "[deleted]",
        "[removed by reddit]",
        "[unavailable]",
    }
)

MARKDOWN_LINK_PATTERN = re.compile(r"!\[[^\]]*\]\([^)]+\)|\[[^\]]+\]\([^)]+\)")
DIRECT_URL_PATTERN = re.compile(
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
    r"|www\.(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),])+"
    r"|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)
MEDIA_HOST_PATTERN = re.compile(
    r"(?i)\b(?:imgur|i\.redd\.it|v\.redd\.it|youtube|youtu\.be|gfycat|redgifs)\b"
)
MENTION_PATTERN = re.compile(r"(?i)(?:u/|r/)")


def check_if_body_not_removed(text: str) -> bool:
    """Reject Reddit deleted/removed/unavailable comment sentinel bodies."""
    return text.strip().lower() not in REMOVED_BODY_SENTINELS


def check_if_no_reddit_mentions(text: str) -> bool:
    """Reject comments containing user or subreddit mention tokens."""
    return MENTION_PATTERN.search(text) is None


def check_if_no_markdown_links(text: str) -> bool:
    """Reject markdown links and images embedded in comment text."""
    return MARKDOWN_LINK_PATTERN.search(text) is None


def check_if_no_direct_urls(text: str) -> bool:
    """Reject comments containing direct URLs or bare domains."""
    return DIRECT_URL_PATTERN.search(text) is None


def check_if_no_media_hosts(text: str) -> bool:
    """Reject comments referencing common image/video host patterns."""
    return MEDIA_HOST_PATTERN.search(text) is None


def check_if_not_automoderator(author: str) -> bool:
    """Reject AutoModerator-authored comments."""
    return author.strip().casefold() != "automoderator"
