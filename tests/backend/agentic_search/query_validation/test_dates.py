"""Date bounds the program fills in when a question leaves a side open."""

from __future__ import annotations

import urllib.request
from datetime import date, timedelta

import pytest

from backend.agentic_search.query_validation.check_data_availability import (
    check_data_availability,
)
from backend.agentic_search.query_validation.models import TableMetadata, ValidationIssue
from backend.agentic_search.query_validation.query_intent import dates
from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.constants import DATA_START_DATE, RecordType

# A fixed UTC day. resolve_dates reads it through get_current_date.
TODAY = date(2026, 10, 27)
YESTERDAY = TODAY - timedelta(days=1)
DEBATE = "Show the text of posts from the week of the debate that say climate."


@pytest.fixture
def today(monkeypatch: pytest.MonkeyPatch) -> date:
    """Pin the UTC clock and refuse any live HTTP call."""

    monkeypatch.setattr(dates, "get_current_date", lambda: TODAY)

    def blocked_urlopen(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("unit test made a network call")

    monkeypatch.setattr(urllib.request, "urlopen", blocked_urlopen)
    return TODAY


def test_no_dates_use_a_seven_day_window_ending_today(today: date) -> None:
    unresolved = dates.resolve_dates("how many posts say climate", None, None)
    invented = dates.resolve_dates(
        "how many posts say climate",
        date(2026, 1, 1),
        date(2026, 1, 31),
    )

    assert unresolved == invented
    assert unresolved.end_date == today
    assert unresolved.start_date == today - timedelta(days=dates.START_LOOKBACK_DAYS)
    assert unresolved.start_date_inferred is True
    assert unresolved.end_date_inferred is True


def test_open_window_covers_eight_inclusive_days(today: date) -> None:
    resolved = dates.resolve_dates("how many posts say climate", None, None)
    assert resolved.start_date is not None
    assert resolved.end_date == today
    inclusive_days = (resolved.end_date - resolved.start_date).days + 1
    assert inclusive_days == dates.START_LOOKBACK_DAYS + 1
    assert inclusive_days == 8


def test_start_before_data_start_is_refused(today: date) -> None:
    """An inferred start before 1 Aug 2026 is out of coverage. It is not clamped."""

    assert DATA_START_DATE == date(2026, 8, 1)
    resolved = dates.resolve_dates(
        "posts until 2026-08-03",
        date(2026, 8, 1),
        date(2026, 8, 3),
    )
    assert resolved.start_date == date(2026, 7, 27)
    assert resolved.end_date == date(2026, 8, 3)
    assert resolved.start_date_inferred is True
    assert resolved.end_date_inferred is False
    assert resolved.start_date < DATA_START_DATE

    intent = QueryIntent(
        is_nonsense=False,
        record_type=RecordType.POSTS,
        columns=["text", "created_at"],
        start_date=resolved.start_date,
        end_date=resolved.end_date,
        start_date_inferred=resolved.start_date_inferred,
        end_date_inferred=resolved.end_date_inferred,
    )
    snapshot = {
        RecordType.POSTS: TableMetadata(
            columns=("text", "created_at"),
            coverage_start=DATA_START_DATE,
            coverage_end=today,
        )
    }
    assert check_data_availability(intent, snapshot) == [ValidationIssue.RANGE_OUTSIDE_COVERAGE]


def test_from_may_keeps_the_whole_month(today: date) -> None:
    """'from' alone is not an open start, so May stays 1 May through 31 May."""

    query = "posts from May 2026"
    assert dates._regex_sides(query) == "both"
    resolved = dates.resolve_dates(query, date(2026, 5, 1), date(2026, 5, 31))
    assert resolved.start_date == date(2026, 5, 1)
    assert resolved.end_date == date(2026, 5, 31)
    assert resolved.start_date_inferred is False
    assert resolved.end_date_inferred is False
    assert resolved.end_date != today


def test_since_yesterday_fills_the_end(today: date) -> None:
    resolved = dates.resolve_dates(
        "posts since yesterday",
        YESTERDAY,
        date(2026, 10, 1),
    )
    assert resolved.start_date == YESTERDAY
    assert resolved.end_date == today
    assert resolved.start_date_inferred is False
    assert resolved.end_date_inferred is True


def test_until_yesterday_fills_the_start(today: date) -> None:
    resolved = dates.resolve_dates(
        "posts until yesterday",
        date(2026, 10, 1),
        YESTERDAY,
    )
    assert resolved.end_date == YESTERDAY
    assert resolved.start_date == YESTERDAY - timedelta(days=dates.START_LOOKBACK_DAYS)
    assert resolved.start_date_inferred is True
    assert resolved.end_date_inferred is False


def test_regex_defers_an_ambiguous_phrase_and_jev_is_mocked(
    monkeypatch: pytest.MonkeyPatch,
    today: date,
) -> None:
    """A phrase the regex cannot classify must not make a live call.

    When the Jev client is on this branch, the mocked choice is ``neither``
    and the seven-day window is used. Before that client exists, the parsed
    dates stay.
    """

    assert dates._regex_sides(DEBATE) is None
    calls = {"n": 0}

    def fake_choice(*_args: object, **_kwargs: object) -> str:
        calls["n"] += 1
        return "neither"

    monkeypatch.setattr(dates, "ask_choice", fake_choice, raising=False)
    invented_start = date(2026, 9, 1)
    invented_end = date(2026, 9, 7)
    resolved = dates.resolve_dates(DEBATE, invented_start, invented_end)

    if calls["n"] == 0:
        assert resolved.start_date == invented_start
        assert resolved.end_date == invented_end
        assert resolved.start_date_inferred is False
        assert resolved.end_date_inferred is False
        return

    assert calls["n"] == 1
    assert resolved.end_date == today
    assert resolved.start_date == today - timedelta(days=dates.START_LOOKBACK_DAYS)
    assert resolved.start_date_inferred is True
    assert resolved.end_date_inferred is True
