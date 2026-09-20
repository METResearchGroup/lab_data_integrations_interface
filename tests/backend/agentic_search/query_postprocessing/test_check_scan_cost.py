"""The estimate reads Iceberg metadata, so it runs against a real local table."""

from __future__ import annotations

from datetime import date

import pytest
from pyiceberg.catalog import Catalog

from backend.agentic_search.query_postprocessing import check_scan_cost
from backend.agentic_search.query_postprocessing.check_scan_cost import (
    estimate_scan_bytes,
    reason_over_scan_limit,
)
from backend.agentic_search.query_validation.query_intent.models import QueryIntent
from bluesky_ingestion_jetstream.aws.constants import GLUE_DATABASE
from bluesky_ingestion_jetstream.constants import RecordType
from tests.backend.agentic_search.conftest import POST_DAYS


def _intent(
    columns: list[str] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> QueryIntent:
    return QueryIntent(
        is_nonsense=False,
        record_type=RecordType.POSTS,
        columns=columns or [],
        start_date=start_date,
        end_date=end_date,
    )


@pytest.fixture
def table(catalog: Catalog):
    return catalog.load_table((GLUE_DATABASE, RecordType.POSTS))


def test_narrower_date_range_scans_less(table) -> None:
    """The point of the check: the dates prune whole files before anything runs."""

    one_day = estimate_scan_bytes(table, _intent(start_date=POST_DAYS[0], end_date=POST_DAYS[0]))
    all_days = estimate_scan_bytes(table, _intent(start_date=POST_DAYS[0], end_date=POST_DAYS[-1]))

    assert 0 < one_day < all_days


def test_unbounded_dates_scan_every_file(table) -> None:
    bounded = estimate_scan_bytes(table, _intent(start_date=POST_DAYS[0], end_date=POST_DAYS[0]))

    assert estimate_scan_bytes(table, _intent()) > bounded


def test_range_outside_the_data_scans_nothing(table) -> None:
    empty = _intent(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))

    assert estimate_scan_bytes(table, empty) == 0


def test_fewer_columns_scan_less(table) -> None:
    """Athena reads only the column chunks it needs, and so does the estimate."""

    everything = estimate_scan_bytes(table, _intent())
    one_column = estimate_scan_bytes(table, _intent(columns=["langs"]))
    with_text = estimate_scan_bytes(table, _intent(columns=["langs", "text"]))

    assert 0 < one_column < with_text < everything


def test_nested_column_is_counted(table) -> None:
    """`langs` is a list, whose bytes are recorded against its element field."""

    assert estimate_scan_bytes(table, _intent(columns=["langs"])) > 0


def test_small_scan_is_allowed(table) -> None:
    """The fixture holds a few hundred KB, far under the 10 GB cap."""

    assert reason_over_scan_limit(table, _intent()) is None


def test_scan_over_the_cap_is_refused(table, monkeypatch) -> None:
    monkeypatch.setattr(check_scan_cost, "MAX_SCAN_BYTES", 1)
    rejection = reason_over_scan_limit(table, _intent())

    assert rejection is not None
    assert "over the" in rejection
