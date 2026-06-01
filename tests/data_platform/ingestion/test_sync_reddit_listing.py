from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from data_platform.ingestion import sync_reddit


def test_get_subreddit_listing_top_passes_time_filter() -> None:
    subreddit_obj = MagicMock()
    subreddit_obj.top.return_value = iter([])

    sync_reddit._get_subreddit_listing(
        subreddit_obj,
        "top",
        300,
        time_filter="month",
    )

    subreddit_obj.top.assert_called_once_with(limit=300, time_filter="month")


def test_resolve_listing_time_filter_rejects_non_top_listing() -> None:
    fetch = {"listing_time_filter": "month"}
    with pytest.raises(ValueError, match="only valid when listing is 'top'"):
        sync_reddit._resolve_listing_time_filter(fetch, "hot")


def test_resolve_listing_time_filter_rejects_invalid_value() -> None:
    fetch = {"listing_time_filter": "fortnight"}
    with pytest.raises(ValueError, match="Unsupported fetch.listing_time_filter"):
        sync_reddit._resolve_listing_time_filter(fetch, "top")
