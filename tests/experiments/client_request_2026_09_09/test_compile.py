"""Tests for compile_outputs()."""

import json
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from experiments.client_request_2026_09_09.compile import compile_outputs
from experiments.client_request_2026_09_09.constants import (
    CANDIDATES,
    S3_PREFIX,
    Candidate,
)
from experiments.client_request_2026_09_09.export import CandidateExportResult
from experiments.client_request_2026_09_09.schemas import COMBINED_COLUMNS
from tests.experiments.client_request_2026_09_09.conftest import (
    DEFAULT_RUN_TIMESTAMP,
    FakeS3Client,
    sample_row,
    write_combined_rows,
)

RUN_DATE = date(2026, 9, 9)
SHARED_URI = "at://did:plc:shared/app.bsky.feed.post/1"
NAME_MATCH_NOTE = "Rows are name matches on post text, not posts labeled as criticisms."
COVERAGE_NOTE = (
    "Query windows start on max(primary_date, 2026-08-01). "
    "Jetstream Iceberg coverage of posts begins 2026-08-01."
)
ROW_COUNTS = (1, 0, 2, 0, 1)


def _export_for(
    candidate: Candidate,
    parquet_path: Path,
    row_count: int,
) -> CandidateExportResult:
    return CandidateExportResult(
        candidate_id=candidate.candidate_id,
        display_name=candidate.display_name,
        sql="UNLOAD (...)",
        parquet_path=parquet_path,
        s3_parquet_uri=(
            f"s3://lab-data-integrations-interface/{S3_PREFIX}/"
            f"{DEFAULT_RUN_TIMESTAMP}/{candidate.candidate_id}.parquet"
        ),
        row_count=row_count,
    )


SHARED_URI_CANDIDATE_IDS = frozenset({"el_sayed", "ossoff"})


def _rows_for_count(candidate: Candidate, row_count: int) -> list[dict]:
    rows = []
    name_string = candidate.name_strings[0]
    for index in range(row_count):
        uses_shared_uri = candidate.candidate_id in SHARED_URI_CANDIDATE_IDS and index == 0
        uri = SHARED_URI if uses_shared_uri else f"{SHARED_URI}-{candidate.candidate_id}-{index}"
        rows.append(
            sample_row(
                uri=uri,
                matched_candidate=candidate.candidate_id,
                matched_name_string=name_string,
                text=f"mention {name_string}",
            )
        )
    return rows


def _write_five_exports(tmp_path: Path) -> list[CandidateExportResult]:
    exports = []
    for candidate, row_count in zip(CANDIDATES, ROW_COUNTS, strict=True):
        parquet_path = tmp_path / f"{candidate.candidate_id}.parquet"
        write_combined_rows(parquet_path, _rows_for_count(candidate, row_count))
        exports.append(_export_for(candidate, parquet_path, row_count))
    return exports


class TestCompileOutputs:
    """Tests for compile_outputs()."""

    def test_keeps_shared_uris_across_candidates(self, tmp_path):
        """A uri that matches two candidates appears twice in posts.parquet."""
        # Arrange
        exports = _write_five_exports(tmp_path)
        s3_client = FakeS3Client()
        output_dir = tmp_path / "compiled"

        # Act
        result = compile_outputs(
            DEFAULT_RUN_TIMESTAMP,
            RUN_DATE,
            output_dir,
            exports,
            s3_client,
        )
        table = pq.read_table(result.posts_path)
        shared_rows = [
            uri for uri in table.column("uri").to_pylist() if uri == SHARED_URI
        ]

        # Assert
        assert len(shared_rows) == 2

    def test_combined_column_order(self, tmp_path):
        """posts.parquet columns match COMBINED_COLUMNS."""
        # Arrange
        exports = _write_five_exports(tmp_path)
        expected = list(COMBINED_COLUMNS)

        # Act
        result = compile_outputs(
            DEFAULT_RUN_TIMESTAMP,
            RUN_DATE,
            tmp_path / "compiled",
            exports,
            FakeS3Client(),
        )
        table = pq.read_table(result.posts_path)

        # Assert
        assert table.column_names == expected

    def test_metadata_row_counts_and_total_rows(self, tmp_path):
        """Metadata uses export row_counts 1,0,2,0,1 and total_rows is 4."""
        # Arrange
        exports = _write_five_exports(tmp_path)
        expected_counts = list(ROW_COUNTS)
        expected_total = 4

        # Act
        result = compile_outputs(
            DEFAULT_RUN_TIMESTAMP,
            RUN_DATE,
            tmp_path / "compiled",
            exports,
            FakeS3Client(),
        )
        metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        counts = [item["row_count"] for item in metadata["candidates"]]

        # Assert
        assert counts == expected_counts
        assert result.total_rows == expected_total

    def test_cooper_query_start_and_primary_date(self, tmp_path):
        """Cooper metadata records the March primary and August coverage start."""
        # Arrange
        exports = _write_five_exports(tmp_path)

        # Act
        result = compile_outputs(
            DEFAULT_RUN_TIMESTAMP,
            RUN_DATE,
            tmp_path / "compiled",
            exports,
            FakeS3Client(),
        )
        metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        cooper = next(item for item in metadata["candidates"] if item["candidate_id"] == "cooper")

        # Assert
        assert cooper["query_start"] == "2026-08-01"
        assert cooper["primary_date"] == "2026-03-03"

    def test_el_sayed_query_start_is_primary(self, tmp_path):
        """El-Sayed metadata query_start is 2026-08-04."""
        # Arrange
        exports = _write_five_exports(tmp_path)

        # Act
        result = compile_outputs(
            DEFAULT_RUN_TIMESTAMP,
            RUN_DATE,
            tmp_path / "compiled",
            exports,
            FakeS3Client(),
        )
        metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        el_sayed = next(
            item for item in metadata["candidates"] if item["candidate_id"] == "el_sayed"
        )

        # Assert
        assert el_sayed["query_start"] == "2026-08-04"

    def test_criticism_flag_and_notes(self, tmp_path):
        """is_criticism_filter is false and notes contain both pinned strings."""
        # Arrange
        exports = _write_five_exports(tmp_path)

        # Act
        result = compile_outputs(
            DEFAULT_RUN_TIMESTAMP,
            RUN_DATE,
            tmp_path / "compiled",
            exports,
            FakeS3Client(),
        )
        metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))

        # Assert
        assert metadata["is_criticism_filter"] is False
        assert NAME_MATCH_NOTE in metadata["notes"]
        assert COVERAGE_NOTE in metadata["notes"]
        assert metadata["candidates"][0]["s3_parquet_uri"].endswith("el_sayed.parquet")

    def test_missing_ossoff_raises_value_error(self, tmp_path):
        """A multi-candidate list missing ossoff raises ValueError naming ossoff."""
        # Arrange
        exports = [
            item
            for item in _write_five_exports(tmp_path)
            if item.candidate_id != "ossoff"
        ]

        # Act / Assert
        with pytest.raises(ValueError, match="ossoff"):
            compile_outputs(
                DEFAULT_RUN_TIMESTAMP,
                RUN_DATE,
                tmp_path / "compiled",
                exports,
                FakeS3Client(),
            )

    def test_uploads_posts_and_metadata_under_run_prefix(self, tmp_path):
        """compile uploads posts.parquet and metadata.json under the run prefix."""
        # Arrange
        exports = _write_five_exports(tmp_path)
        s3_client = FakeS3Client()
        expected_prefix = f"{S3_PREFIX}/{DEFAULT_RUN_TIMESTAMP}/"

        # Act
        compile_outputs(
            DEFAULT_RUN_TIMESTAMP,
            RUN_DATE,
            tmp_path / "compiled",
            exports,
            s3_client,
        )
        uploaded_keys = {key for _, _, key in s3_client.uploads}

        # Assert
        assert f"{expected_prefix}posts.parquet" in uploaded_keys
        assert f"{expected_prefix}metadata.json" in uploaded_keys
        s3_client.delete_objects.assert_not_called()
