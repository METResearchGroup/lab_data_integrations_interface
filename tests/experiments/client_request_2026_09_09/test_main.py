"""Tests for main.run() and CLI parsing."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from experiments.client_request_2026_09_09.constants import CANDIDATES, SMOKE_LIMIT
from experiments.client_request_2026_09_09.export import CandidateExportResult
from experiments.client_request_2026_09_09.main import main, run
from experiments.client_request_2026_09_09.report import PROGRESS_TABLE_HEADER
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


def _stub_export_result(candidate_id: str, tmp_path: Path) -> CandidateExportResult:
    candidate = candidate_by_id(candidate_id)
    parquet_path = tmp_path / f"{candidate_id}.parquet"
    write_combined_rows(
        parquet_path,
        [
            sample_row(
                uri=f"at://did:plc:test/app.bsky.feed.post/{candidate_id}",
                matched_candidate=candidate_id,
                matched_name_string=candidate.name_strings[0],
            )
        ],
    )
    return CandidateExportResult(
        candidate_id=candidate.candidate_id,
        display_name=candidate.display_name,
        sql=f"UNLOAD ( SELECT * FROM posts WHERE '{candidate_id}' )",
        parquet_path=parquet_path,
        s3_parquet_uri=(
            "s3://lab-data-integrations-interface/experiments/client_request_2026_09_09/"
            f"{DEFAULT_RUN_TIMESTAMP}/{candidate_id}.parquet"
        ),
        row_count=1,
    )


def _register_one_row_parts(s3_client: FakeS3Client, tmp_path: Path) -> None:
    for candidate in CANDIDATES:
        part_path = tmp_path / "parts" / f"{candidate.candidate_id}.parquet"
        write_combined_rows(
            part_path,
            [
                sample_row(
                    uri=f"at://did:plc:test/app.bsky.feed.post/{candidate.candidate_id}",
                    matched_candidate=candidate.candidate_id,
                    matched_name_string=candidate.name_strings[0],
                    text=f"hello {candidate.name_strings[0]}",
                )
            ],
        )
        s3_client.register_object(
            unload_part_key(DEFAULT_RUN_TIMESTAMP, candidate.candidate_id),
            part_path,
        )


class TestRun:
    """Tests for run()."""

    def test_full_run_writes_posts_and_five_candidate_metadata(self, tmp_path):
        """Injected fakes produce posts.parquet whose metadata row_counts sum."""
        # Arrange
        athena = FakeAthena()
        s3_client = FakeS3Client()
        _register_one_row_parts(s3_client, tmp_path)

        # Act
        result = run(
            athena=athena,
            s3_client=s3_client,
            output_root=tmp_path,
            run_timestamp=DEFAULT_RUN_TIMESTAMP,
            run_date=RUN_DATE,
        )
        metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        counts = [item["row_count"] for item in metadata["candidates"]]

        # Assert
        assert result.posts_path.is_file()
        assert len(metadata["candidates"]) == 5
        assert sum(counts) == result.total_rows == 5

    def test_candidate_cooper_exports_once(self, tmp_path, monkeypatch):
        """--candidate cooper calls export_candidate once and metadata has cooper."""
        # Arrange
        export_mock = MagicMock(return_value=_stub_export_result("cooper", tmp_path))
        monkeypatch.setattr(
            "experiments.client_request_2026_09_09.main.export_candidate",
            export_mock,
        )

        # Act
        result = run(
            candidate_id="cooper",
            athena=FakeAthena(),
            s3_client=FakeS3Client(),
            output_root=tmp_path,
            run_timestamp=DEFAULT_RUN_TIMESTAMP,
            run_date=RUN_DATE,
        )
        metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))

        # Assert
        assert export_mock.call_count == 1
        assert len(metadata["candidates"]) == 1
        assert metadata["candidates"][0]["candidate_id"] == "cooper"

    def test_smoke_passes_limit_100_to_every_export(self, tmp_path, monkeypatch):
        """--smoke passes smoke_limit 100 into every export_candidate call."""
        # Arrange
        export_mock = MagicMock(
            side_effect=lambda candidate, *args, **kwargs: _stub_export_result(
                candidate.candidate_id, tmp_path
            )
        )
        monkeypatch.setattr(
            "experiments.client_request_2026_09_09.main.export_candidate",
            export_mock,
        )
        monkeypatch.setattr(
            "experiments.client_request_2026_09_09.main.compile_outputs",
            MagicMock(),
        )

        # Act
        run(
            smoke=True,
            athena=FakeAthena(),
            s3_client=FakeS3Client(),
            output_root=tmp_path,
            run_timestamp=DEFAULT_RUN_TIMESTAMP,
            run_date=RUN_DATE,
        )

        # Assert
        assert export_mock.call_count == len(CANDIDATES)
        for call in export_mock.call_args_list:
            assert call.kwargs["smoke_limit"] == SMOKE_LIMIT == 100

    def test_second_export_failure_skips_compile(self, tmp_path, monkeypatch):
        """If the second export raises, compile_outputs is not called."""
        # Arrange
        first = _stub_export_result("el_sayed", tmp_path)
        export_mock = MagicMock(side_effect=[first, RuntimeError("Athena query FAILED")])
        compile_mock = MagicMock()
        monkeypatch.setattr(
            "experiments.client_request_2026_09_09.main.export_candidate",
            export_mock,
        )
        monkeypatch.setattr(
            "experiments.client_request_2026_09_09.main.compile_outputs",
            compile_mock,
        )

        # Act / Assert
        with pytest.raises(RuntimeError, match="Athena query FAILED"):
            run(
                athena=FakeAthena(),
                s3_client=FakeS3Client(),
                output_root=tmp_path,
                run_timestamp=DEFAULT_RUN_TIMESTAMP,
                run_date=RUN_DATE,
            )
        compile_mock.assert_not_called()
        assert not (tmp_path / DEFAULT_RUN_TIMESTAMP / "posts.parquet").exists()

    def test_two_exports_print_two_full_tables(self, tmp_path, monkeypatch, capsys):
        """Each finished query reprints the full table with the contract header."""
        # Arrange
        two_candidates = CANDIDATES[:2]
        monkeypatch.setattr(
            "experiments.client_request_2026_09_09.main.CANDIDATES",
            two_candidates,
        )
        export_mock = MagicMock(
            side_effect=lambda candidate, *args, **kwargs: _stub_export_result(
                candidate.candidate_id, tmp_path
            )
        )
        monkeypatch.setattr(
            "experiments.client_request_2026_09_09.main.export_candidate",
            export_mock,
        )
        monkeypatch.setattr(
            "experiments.client_request_2026_09_09.main.compile_outputs",
            MagicMock(),
        )

        # Act
        run(
            athena=FakeAthena(),
            s3_client=FakeS3Client(),
            output_root=tmp_path,
            run_timestamp=DEFAULT_RUN_TIMESTAMP,
            run_date=RUN_DATE,
        )
        stdout = capsys.readouterr().out

        # Assert
        assert stdout.count(PROGRESS_TABLE_HEADER) == 2
        sections = stdout.split(PROGRESS_TABLE_HEADER)
        second_table = sections[2]
        data_rows = [
            line
            for line in second_table.splitlines()
            if line.startswith("|") and "---" not in line
        ]
        assert len(data_rows) == 2


class TestMain:
    """Tests for main() CLI parsing."""

    def test_invalid_candidate_exits_2(self, capsys):
        """An unknown --candidate value exits with code 2 and lists valid ids."""
        # Arrange
        invalid_id = "nope"
        expected_ids = tuple(candidate.candidate_id for candidate in CANDIDATES)

        # Act
        with pytest.raises(SystemExit) as exc_info:
            main(["--candidate", invalid_id])
        stderr = capsys.readouterr().err

        # Assert
        assert exc_info.value.code == 2
        for candidate_id in expected_ids:
            assert candidate_id in stderr
