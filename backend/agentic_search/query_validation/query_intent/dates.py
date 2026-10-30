"""Resolves a question's date bounds, then fills any side the question left open."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from lib.timestamp_utils import get_current_date
from ml_tooling.llm.jev import ask_choice, last_status

# Seven days before the end date. The inclusive window is eight calendar days.
START_LOOKBACK_DAYS = 7

_SIDES = ("both", "start_only", "end_only", "neither")
_BOUNDS_INSTRUCTIONS = (
    "Which date bounds does this question state? "
    "A named month, a calendar year, a single day, 'the last N days', "
    "'through', 'between', or 'from X to Y' is both. "
    "'since' or 'after' with no 'until' or 'before' is start_only, "
    "including 'since yesterday'. "
    "'until' or 'before' with no 'since' or 'after' is end_only. "
    "No date language is neither. "
    "'from' by itself is not an open start."
)
_BOUNDS_CRITERIA = {
    "both": "The question states a start and an end.",
    "start_only": "The question states a start and no end.",
    "end_only": "The question states an end and no start.",
    "neither": "The question states no date bound.",
}

_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_MONTH = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b"
)
_RELATIVE = re.compile(
    r"\b(?:yesterday|today|last\s+(?:\d+\s+)?(?:day|week|month)s?|"
    r"last\s+\w+\s+(?:day|week|month)s?)\b"
)
_BOUND_WORD = re.compile(r"\b(?:since|after|before|until|from|through|between)\b")
_START_WORD = re.compile(r"\b(?:since|after)\b")
_END_WORD = re.compile(r"\b(?:until|before)\b")
_CLOSED_WORD = re.compile(r"\b(?:through|between)\b")
_FROM_TO = re.compile(r"\bfrom\b.+\b(?:to|through)\b")


@dataclass(frozen=True)
class ResolvedDates:
    """The range a query will scan, and which sides the program filled in."""

    start_date: date | None
    end_date: date | None
    start_date_inferred: bool
    end_date_inferred: bool


def resolve_dates(
    query: str,
    stated_start: date | None,
    stated_end: date | None,
) -> ResolvedDates:
    """Return the scan range for ``query``.

    A side the question states is kept from the parsed dates. A missing end
    becomes the current UTC date. A missing start becomes that end minus
    ``START_LOOKBACK_DAYS``. A stated side that did not parse stays empty.

    Examples
    --------
    Neither side stated, with today 2026-10-24, returns start 2026-10-17
    and end 2026-10-24, and both inferred flags are true.
    """

    sides = _stated_sides(query, stated_start, stated_end)
    start = stated_start if sides in ("both", "start_only") else None
    end = stated_end if sides in ("both", "end_only") else None
    end_inferred = False
    start_inferred = False
    if sides in ("start_only", "neither") and end is None:
        end = get_current_date()
        end_inferred = True
    if sides in ("end_only", "neither") and start is None and end is not None:
        start = end - timedelta(days=START_LOOKBACK_DAYS)
        start_inferred = True
    return ResolvedDates(start, end, start_inferred, end_inferred)


def _stated_sides(
    query: str,
    stated_start: date | None,
    stated_end: date | None,
) -> str:
    found = _regex_sides(query)
    if found is None:
        found = _jev_sides(query)
    if found is None:
        found = _sides_from_dates(stated_start, stated_end)
    return found


def _regex_sides(query: str) -> str | None:
    """Classify an obvious date phrase. None means the phrase needs Jev.

    "since" and "after" are a start only, and "until" and "before" are an
    end only, including when the day is relative ("since yesterday"). A
    relative day with no open word is both sides.
    """

    text = query.lower()
    if not _has_time_language(text):
        return "neither"
    if _is_closed_span(text):
        return "both"
    startish = _START_WORD.search(text) is not None
    endish = _END_WORD.search(text) is not None
    if startish and endish:
        return "both"
    if startish:
        return "start_only"
    if endish:
        return "end_only"
    if _RELATIVE.search(text) or _ISO.search(text) or _MONTH.search(text) or _YEAR.search(text):
        return "both"
    return None


def _has_time_language(text: str) -> bool:
    return any(pattern.search(text) for pattern in (_ISO, _YEAR, _MONTH, _RELATIVE, _BOUND_WORD))


def _is_closed_span(text: str) -> bool:
    if _CLOSED_WORD.search(text):
        return True
    return _FROM_TO.search(text) is not None


def _sides_from_dates(stated_start: date | None, stated_end: date | None) -> str:
    if stated_start is not None and stated_end is not None:
        return "both"
    if stated_start is not None:
        return "start_only"
    if stated_end is not None:
        return "end_only"
    return "neither"


def last_jev_status() -> str:
    """A short status from the last Jev call, with no response body."""

    return last_status()


def _jev_sides(query: str) -> str | None:
    """Ask Jev which bounds the question states. None when the call cannot answer."""

    return ask_choice(
        query,
        question_id="bounds",
        instructions=_BOUNDS_INSTRUCTIONS,
        criteria=_BOUNDS_CRITERIA,
        allowed=_SIDES,
    )
