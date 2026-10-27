"""Prints the filled date range for the open-bound rules. No model call.

Run from the project root:
  python -m backend.agentic_search.smoke_tests.check_keyword_search
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.agentic_search.query_validation.query_intent.dates import (
    _regex_sides,
    resolve_dates,
)
from lib.timestamp_utils import get_current_date


def check_date_rules() -> list[str]:
    """The fill rules, with the dates the model would have copied. No model call."""

    today = get_current_date()
    yesterday = today - timedelta(days=1)
    august = date(2026, 8, 1)
    invented = date(2026, 8, 31)
    cases = (
        (
            "since yesterday",
            "posts since yesterday that say climate",
            yesterday,
            invented,
            yesterday,
            today,
            False,
            True,
        ),
        (
            "until yesterday",
            "posts until yesterday that say climate",
            invented,
            yesterday,
            yesterday - timedelta(days=7),
            yesterday,
            True,
            False,
        ),
        (
            "named month",
            "posts in August 2026 that say climate",
            august,
            invented,
            august,
            invented,
            False,
            False,
        ),
        (
            "from a month",
            "posts from May 2026 that say climate",
            date(2026, 5, 1),
            date(2026, 5, 31),
            date(2026, 5, 1),
            date(2026, 5, 31),
            False,
            False,
        ),
    )
    print("\n--- date rules ---")
    failures = []
    for name, query, stated_start, stated_end, start, end, start_inferred, end_inferred in cases:
        resolved = resolve_dates(query, stated_start, stated_end)
        ok = (
            resolved.start_date == start
            and resolved.end_date == end
            and resolved.start_date_inferred is start_inferred
            and resolved.end_date_inferred is end_inferred
        )
        print(
            f"  {name}: {resolved.start_date}..{resolved.end_date} "
            f"start_inferred={resolved.start_date_inferred} "
            f"end_inferred={resolved.end_date_inferred}"
        )
        if ok:
            print("  PASS")
        else:
            print(f"  FAIL: expected {start}..{end}")
            failures.append(name)
    ambiguous = "posts from the week of the debate that say climate"
    if _regex_sides(ambiguous) is None:
        print("  ambiguous from-phrase: regex defers")
        print("  PASS")
    else:
        print(f"  FAIL: regex classified the debate week as {_regex_sides(ambiguous)}")
        failures.append("ambiguous from-phrase")
    return failures


def main() -> None:
    failures = check_date_rules()
    if failures:
        raise SystemExit(f"failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
