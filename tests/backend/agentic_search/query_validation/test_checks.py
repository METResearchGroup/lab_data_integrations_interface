"""The checks, driven by intents an extraction would plausibly produce."""

from __future__ import annotations

from datetime import date

from backend.agentic_search.query_validation.check_data_availability import (
    check_data_availability,
)
from backend.agentic_search.query_validation.check_data_types import check_data_types
from backend.agentic_search.query_validation.check_nonsense import check_nonsense
from backend.agentic_search.query_validation.models import TableMetadata, ValidationIssue
from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.constants import RecordType

# "how many posts were written in Spanish in July"
CLEAN = QueryIntent(
    is_nonsense=False,
    record_type=RecordType.POSTS,
    columns=["langs", "created_at"],
    start_date=date(2026, 7, 1),
    end_date=date(2026, 7, 31),
)

# "show me posts sorted by like count" -- posts has no like_count column.
INVENTED_COLUMN = QueryIntent(
    is_nonsense=False,
    record_type=RecordType.POSTS,
    columns=["like_count"],
    start_date=None,
    end_date=None,
)

# "who followed whom back in January" -- follows only starts 2026-03-15.
BEFORE_COVERAGE = QueryIntent(
    is_nonsense=False,
    record_type=RecordType.FOLLOWS,
    columns=["author_did", "subject_did", "created_at"],
    start_date=date(2026, 1, 1),
    end_date=date(2026, 1, 31),
)

# "what's the weather in Tokyo"
NONSENSE = QueryIntent(
    is_nonsense=True,
    record_type=None,
    columns=[],
    start_date=None,
    end_date=None,
)

# "how much engagement was there last spring" -- ours, but no table named.
UNRESOLVED_TABLE = QueryIntent(
    is_nonsense=False,
    record_type=None,
    columns=["created_at"],
    start_date=date(2026, 4, 1),
    end_date=date(2026, 5, 31),
)

# "how many posts total" -- both bounds open.
OPEN_BOUNDS = QueryIntent(
    is_nonsense=False,
    record_type=RecordType.POSTS,
    columns=["uri"],
    start_date=None,
    end_date=None,
)


def test_nonsense_is_flagged() -> None:
    assert check_nonsense(NONSENSE) == [ValidationIssue.NONSENSE]


def test_answerable_query_is_not_nonsense() -> None:
    assert check_nonsense(CLEAN) == []


def test_clean_intent_passes_every_check(snapshot: dict[RecordType, TableMetadata]) -> None:
    assert check_nonsense(CLEAN) == []
    assert check_data_types(CLEAN, snapshot) == []
    assert check_data_availability(CLEAN, snapshot) == []


def test_invented_column_is_flagged(snapshot: dict[RecordType, TableMetadata]) -> None:
    assert check_data_types(INVENTED_COLUMN, snapshot) == [ValidationIssue.UNKNOWN_COLUMN]


def test_unresolved_record_type_is_flagged(snapshot: dict[RecordType, TableMetadata]) -> None:
    assert check_data_types(UNRESOLVED_TABLE, snapshot) == [ValidationIssue.UNKNOWN_RECORD_TYPE]


def test_record_type_absent_from_snapshot_is_unknown(
    snapshot: dict[RecordType, TableMetadata],
) -> None:
    reposts = QueryIntent(
        is_nonsense=False,
        record_type=RecordType.REPOSTS,
        columns=["uri"],
        start_date=None,
        end_date=None,
    )
    assert check_data_types(reposts, snapshot) == [ValidationIssue.UNKNOWN_RECORD_TYPE]


def test_columns_are_checked_against_the_requested_table_only(
    snapshot: dict[RecordType, TableMetadata],
) -> None:
    """subject_uri is a likes column, so asking posts for it is an unknown column."""

    intent = QueryIntent(
        is_nonsense=False,
        record_type=RecordType.POSTS,
        columns=["subject_uri"],
        start_date=None,
        end_date=None,
    )
    assert check_data_types(intent, snapshot) == [ValidationIssue.UNKNOWN_COLUMN]


def test_range_before_coverage_is_flagged(snapshot: dict[RecordType, TableMetadata]) -> None:
    assert check_data_availability(BEFORE_COVERAGE, snapshot) == [
        ValidationIssue.RANGE_OUTSIDE_COVERAGE
    ]


def test_range_after_coverage_is_flagged(snapshot: dict[RecordType, TableMetadata]) -> None:
    intent = CLEAN.model_copy(update={"end_date": date(2026, 12, 31)})
    assert check_data_availability(intent, snapshot) == [ValidationIssue.RANGE_OUTSIDE_COVERAGE]


def test_open_bounds_ask_for_as_far_as_we_go(snapshot: dict[RecordType, TableMetadata]) -> None:
    assert check_data_availability(OPEN_BOUNDS, snapshot) == []


def test_unresolved_record_type_uses_widest_bounds(
    snapshot: dict[RecordType, TableMetadata],
) -> None:
    """April is outside follows' coverage but inside posts', so the widest bounds allow it."""

    assert check_data_availability(UNRESOLVED_TABLE, snapshot) == []

    before_everything = UNRESOLVED_TABLE.model_copy(update={"start_date": date(2025, 12, 31)})
    assert check_data_availability(before_everything, snapshot) == [
        ValidationIssue.RANGE_OUTSIDE_COVERAGE
    ]


def test_empty_snapshot_reports_no_coverage_issue() -> None:
    assert check_data_availability(CLEAN, {}) == []
