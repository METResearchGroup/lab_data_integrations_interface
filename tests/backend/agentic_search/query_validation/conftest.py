"""Catalog snapshot the query_validation tests check against."""

from __future__ import annotations

from datetime import date

import pytest

from backend.agentic_search.query_validation.models import TableMetadata
from bluesky_ingestion_jetstream.constants import RecordType

TODAY = date(2026, 8, 22)


@pytest.fixture
def snapshot() -> dict[RecordType, TableMetadata]:
    """Three of the four record types, so a resolved-but-absent table stays testable."""

    return {
        RecordType.POSTS: TableMetadata(
            columns=("uri", "author_did", "text", "langs", "created_at"),
            coverage_start=date(2026, 1, 1),
            coverage_end=TODAY,
        ),
        RecordType.LIKES: TableMetadata(
            columns=("uri", "author_did", "subject_uri", "created_at"),
            coverage_start=date(2026, 1, 1),
            coverage_end=TODAY,
        ),
        RecordType.FOLLOWS: TableMetadata(
            columns=("uri", "author_did", "subject_did", "created_at"),
            coverage_start=date(2026, 3, 15),
            coverage_end=TODAY,
        ),
    }
