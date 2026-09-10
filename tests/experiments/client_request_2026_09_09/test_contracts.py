"""Contract tests for candidate identities, windows, columns, and S3 layout."""

from datetime import date

import pytest

from bluesky_ingestion_jetstream.constants import DATA_START_DATE as JETSTREAM_DATA_START_DATE
from experiments.client_request_2026_09_09.constants import (
    CANDIDATES,
    DATA_START_DATE,
    S3_BUCKET,
    S3_PREFIX,
    query_start_date,
)
from experiments.client_request_2026_09_09.report import format_progress_table
from experiments.client_request_2026_09_09.schemas import COMBINED_COLUMNS
from tests.experiments.client_request_2026_09_09.conftest import candidate_by_id

EXPECTED_CANDIDATE_IDS = (
    "el_sayed",
    "talarico",
    "becerra",
    "cooper",
    "ossoff",
)
EXPECTED_QUERY_STARTS = {
    "el_sayed": date(2026, 8, 4),
    "talarico": date(2026, 8, 1),
    "becerra": date(2026, 8, 1),
    "cooper": date(2026, 8, 1),
    "ossoff": date(2026, 8, 1),
}
EXPECTED_COMBINED_COLUMNS = (
    "uri",
    "did",
    "text",
    "created_at",
    "matched_candidate",
    "matched_name_string",
    "url",
)
PROGRESS_TABLE_HEADER = "| Person | Query | Total results | S3 path |"


class TestCandidates:
    """Tests for CANDIDATES identity order and name strings."""

    def test_candidate_ids_are_exact_stable_order(self):
        """The five candidate_id values match the contract order."""
        # Arrange
        expected = EXPECTED_CANDIDATE_IDS

        # Act
        result = tuple(candidate.candidate_id for candidate in CANDIDATES)

        # Assert
        assert result == expected

    def test_cooper_name_strings_are_roy_cooper_only(self):
        """Cooper matches only the given name plus surname."""
        # Arrange
        cooper = candidate_by_id("cooper")
        expected = ("roy cooper",)

        # Act
        result = cooper.name_strings

        # Assert
        assert result == expected

    def test_becerra_includes_misspelling_and_bare_surname(self):
        """Becerra includes the given name, Beccera misspelling, and surname."""
        # Arrange
        becerra = candidate_by_id("becerra")
        expected = ("xavier becerra", "xavier beccera", "becerra")

        # Act
        result = becerra.name_strings

        # Assert
        assert result == expected

    def test_el_sayed_includes_hyphen_spacing_and_closed_variants(self):
        """El-Sayed name strings include hyphen, space, and closed forms."""
        # Arrange
        el_sayed = candidate_by_id("el_sayed")

        # Act
        result = el_sayed.name_strings

        # Assert
        assert "el-sayed" in result
        assert "el sayed" in result
        assert "elsayed" in result


class TestQueryStartDate:
    """Tests for query_start_date()."""

    @pytest.mark.parametrize(
        "candidate_id,expected",
        tuple(EXPECTED_QUERY_STARTS.items()),
    )
    def test_query_start_matches_coverage_floor_table(self, candidate_id, expected):
        """Each primary date maps to the expected query start."""
        # Arrange
        candidate = candidate_by_id(candidate_id)

        # Act
        result = query_start_date(candidate.primary_date)

        # Assert
        assert result == expected


class TestDataStartDate:
    """Tests for DATA_START_DATE re-export."""

    def test_experiment_imports_jetstream_data_start_date(self):
        """The experiment re-exports the Jetstream coverage start object."""
        # Arrange / Act
        result = DATA_START_DATE

        # Assert
        assert result is JETSTREAM_DATA_START_DATE
        assert result == JETSTREAM_DATA_START_DATE


class TestCombinedColumns:
    """Tests for COMBINED_COLUMNS."""

    def test_combined_columns_exact_order(self):
        """Combined Parquet columns match the contract order."""
        # Arrange
        expected = EXPECTED_COMBINED_COLUMNS

        # Act
        result = COMBINED_COLUMNS

        # Assert
        assert result == expected


class TestS3Constants:
    """Tests for S3_BUCKET and S3_PREFIX."""

    def test_bucket_and_prefix(self):
        """S3 layout constants match the experiment prefix contract."""
        # Arrange
        expected_bucket = "lab-data-integrations-interface"
        expected_prefix = "experiments/client_request_2026_09_09"

        # Act
        result_bucket = S3_BUCKET
        result_prefix = S3_PREFIX

        # Assert
        assert result_bucket == expected_bucket
        assert result_prefix == expected_prefix


class TestFormatProgressTable:
    """Tests for format_progress_table()."""

    def test_zero_rows_header_line(self):
        """An empty table still prints the exact progress header."""
        # Arrange
        expected = PROGRESS_TABLE_HEADER

        # Act
        result = format_progress_table([])

        # Assert
        assert result.splitlines()[0] == expected
