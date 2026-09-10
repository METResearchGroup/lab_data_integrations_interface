"""Tests for export_candidate() with fake Athena and S3."""

from datetime import date
from pathlib import Path

import pyarrow.parquet as pq

from experiments.client_request_2026_09_09.constants import (
    GLUE_DATABASE,
    S3_BUCKET,
    S3_PREFIX,
    WORKGROUP,
)
from experiments.client_request_2026_09_09.export import export_candidate
from experiments.client_request_2026_09_09.schemas import ATHENA_COLUMNS
from tests.experiments.client_request_2026_09_09.conftest import (
    DEFAULT_RUN_TIMESTAMP,
    FakeAthena,
    FakeS3Client,
    candidate_by_id,
    sample_row,
    unload_part_key,
    write_combined_rows,
)

RUN_DATE = date(2026, 9, 9)
SMOKE_LIMIT = 100


def _register_cooper_part(s3_client: FakeS3Client, tmp_path: Path) -> Path:
    part_path = tmp_path / "source" / "cooper-part.parquet"
    write_combined_rows(
        part_path,
        [
            sample_row(
                uri="at://did:plc:test/app.bsky.feed.post/1",
                matched_candidate="cooper",
                matched_name_string="roy cooper",
                text="vote roy cooper",
            )
        ],
    )
    s3_client.register_object(
        unload_part_key(DEFAULT_RUN_TIMESTAMP, "cooper"),
        part_path,
    )
    return part_path


class TestExportCandidate:
    """Tests for export_candidate()."""

    def test_happy_path_runs_athena_and_writes_one_row(self, tmp_path):
        """A one-row UNLOAD part becomes a local Parquet with row_count 1."""
        # Arrange
        athena = FakeAthena()
        s3_client = FakeS3Client()
        _register_cooper_part(s3_client, tmp_path)
        output_dir = tmp_path / "out"
        expected_database = "bluesky_raw"
        expected_workgroup = "bluesky_raw_maintenance"

        # Act
        result = export_candidate(
            candidate_by_id("cooper"),
            RUN_DATE,
            DEFAULT_RUN_TIMESTAMP,
            output_dir,
            athena,
            s3_client,
        )

        # Assert
        assert len(athena.queries) == 1
        sql, database, workgroup = athena.queries[0]
        assert database == expected_database == GLUE_DATABASE
        assert workgroup == expected_workgroup == WORKGROUP
        assert result.row_count == 1
        assert result.parquet_path.is_file()
        assert sql.startswith("UNLOAD")

    def test_unload_destination_uses_run_prefix(self, tmp_path):
        """The UNLOAD TO URI contains unload/cooper/ under the run timestamp."""
        # Arrange
        athena = FakeAthena()
        s3_client = FakeS3Client()
        _register_cooper_part(s3_client, tmp_path)
        expected_fragment = (
            f"{S3_PREFIX}/{DEFAULT_RUN_TIMESTAMP}/unload/cooper/"
        )

        # Act
        export_candidate(
            candidate_by_id("cooper"),
            RUN_DATE,
            DEFAULT_RUN_TIMESTAMP,
            tmp_path / "out",
            athena,
            s3_client,
        )

        # Assert
        sql = athena.queries[0][0]
        assert expected_fragment in sql
        assert f"TO 's3://{S3_BUCKET}/{expected_fragment}'" in sql

    def test_merged_parquet_uri_and_upload_key(self, tmp_path):
        """The merged object is <run_timestamp>/cooper.parquet."""
        # Arrange
        athena = FakeAthena()
        s3_client = FakeS3Client()
        _register_cooper_part(s3_client, tmp_path)
        expected_key = f"{S3_PREFIX}/{DEFAULT_RUN_TIMESTAMP}/cooper.parquet"
        expected_uri = f"s3://{S3_BUCKET}/{expected_key}"

        # Act
        result = export_candidate(
            candidate_by_id("cooper"),
            RUN_DATE,
            DEFAULT_RUN_TIMESTAMP,
            tmp_path / "out",
            athena,
            s3_client,
        )

        # Assert
        assert result.s3_parquet_uri == expected_uri
        uploaded_keys = [key for _, bucket, key in s3_client.uploads]
        assert expected_key in uploaded_keys
        assert S3_BUCKET in {bucket for _, bucket, _ in s3_client.uploads}

    def test_empty_unload_writes_zero_row_parquet(self, tmp_path):
        """A successful query with no S3 parts uploads an empty Parquet."""
        # Arrange
        athena = FakeAthena()
        s3_client = FakeS3Client()
        output_dir = tmp_path / "out"

        # Act
        result = export_candidate(
            candidate_by_id("cooper"),
            RUN_DATE,
            DEFAULT_RUN_TIMESTAMP,
            output_dir,
            athena,
            s3_client,
        )

        # Assert
        assert result.row_count == 0
        assert result.parquet_path.is_file()
        table = pq.read_table(result.parquet_path)
        assert table.num_rows == 0
        assert table.column_names == list(ATHENA_COLUMNS)
        expected_key = f"{S3_PREFIX}/{DEFAULT_RUN_TIMESTAMP}/cooper.parquet"
        assert expected_key in {key for _, _, key in s3_client.uploads}

    def test_smoke_limit_is_forwarded_to_sql(self, tmp_path):
        """smoke_limit 100 puts LIMIT 100 in the SQL passed to run_query."""
        # Arrange
        athena = FakeAthena()
        s3_client = FakeS3Client()
        _register_cooper_part(s3_client, tmp_path)

        # Act
        export_candidate(
            candidate_by_id("cooper"),
            RUN_DATE,
            DEFAULT_RUN_TIMESTAMP,
            tmp_path / "out",
            athena,
            s3_client,
            smoke_limit=SMOKE_LIMIT,
        )

        # Assert
        sql = athena.queries[0][0]
        assert "LIMIT 100" in sql

    def test_delete_objects_is_not_called(self, tmp_path):
        """A successful Cooper export does not delete UNLOAD parts."""
        # Arrange
        athena = FakeAthena()
        s3_client = FakeS3Client()
        _register_cooper_part(s3_client, tmp_path)

        # Act
        export_candidate(
            candidate_by_id("cooper"),
            RUN_DATE,
            DEFAULT_RUN_TIMESTAMP,
            tmp_path / "out",
            athena,
            s3_client,
        )

        # Assert
        s3_client.delete_objects.assert_not_called()
