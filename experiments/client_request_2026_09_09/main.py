"""Export Iceberg posts whose text names five Democratic candidates.

Run from the repo root:

    PYTHONPATH=. uv run python experiments/client_request_2026_09_09/main.py
    PYTHONPATH=. uv run python experiments/client_request_2026_09_09/main.py --smoke
    PYTHONPATH=. uv run python experiments/client_request_2026_09_09/main.py --candidate cooper
    PYTHONPATH=. uv run python \\
        experiments/client_request_2026_09_09/main.py --smoke --candidate el_sayed
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from pathlib import Path

import boto3

from experiments.client_request_2026_09_09.compile import CompileResult, compile_outputs
from experiments.client_request_2026_09_09.constants import (
    CANDIDATES,
    CANDIDATES_BY_ID,
    SMOKE_LIMIT,
    Candidate,
)
from experiments.client_request_2026_09_09.export import export_candidate
from experiments.client_request_2026_09_09.report import ProgressRow, format_progress_table
from lib.aws.athena import Athena
from lib.aws.constants import AWS_REGION
from lib.timestamp_utils import get_current_timestamp

EXPERIMENT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_ROOT = EXPERIMENT_DIR / "data"
CANDIDATE_ID_CHOICES = tuple(candidate.candidate_id for candidate in CANDIDATES)


def _selected_candidates(candidate_id: str | None) -> list[Candidate]:
    if candidate_id is None:
        return list(CANDIDATES)
    return [CANDIDATES_BY_ID[candidate_id]]


def _smoke_limit(smoke: bool) -> int | None:
    if smoke:
        return SMOKE_LIMIT
    return None


def _print_compile_summary(compiled: CompileResult) -> None:
    print(compiled.posts_s3_uri)
    print(compiled.metadata_s3_uri)
    print(compiled.total_rows)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI flags for a full run, a smoke cap, or one candidate."""

    parser = argparse.ArgumentParser(
        description="Export Iceberg posts whose text names Democratic candidates.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=f"Cap each Athena export at {SMOKE_LIMIT} rows.",
    )
    parser.add_argument(
        "--candidate",
        choices=CANDIDATE_ID_CHOICES,
        default=None,
        help="Export only this candidate_id, then compile that subset.",
    )
    return parser.parse_args(argv)


def run(
    smoke: bool = False,
    candidate_id: str | None = None,
    athena: Athena | None = None,
    s3_client=None,
    output_root: Path | None = None,
    run_timestamp: str | None = None,
    run_date: date | None = None,
) -> CompileResult:
    """Export selected candidates, print progress, and compile outputs.

    Parameters
    ----------
    smoke
        When true, each export uses ``SMOKE_LIMIT``.
    candidate_id
        If set, export only that id. Must be one of the five ``candidate_id``
        values.
    athena
        Injected Athena client. Defaults to ``Athena()``.
    s3_client
        Injected S3 client. Defaults to boto3 in ``us-east-2``.
    output_root
        Parent of the timestamped output directory. Defaults to ``data/``
        beside this file.
    run_timestamp
        Injected run folder name. Defaults to ``get_current_timestamp()``.
    run_date
        Injected UTC run date. Defaults to today UTC.

    Returns
    -------
    CompileResult
        Combined Parquet and metadata paths after a successful export loop.

    Raises
    ------
    RuntimeError
        When a candidate Athena export fails. Compile is not called.
    """

    resolved_timestamp = (
        run_timestamp if run_timestamp is not None else get_current_timestamp()
    )
    resolved_run_date = run_date if run_date is not None else datetime.now(UTC).date()
    resolved_output_root = output_root if output_root is not None else DEFAULT_OUTPUT_ROOT
    output_dir = resolved_output_root / resolved_timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_athena = athena if athena is not None else Athena()
    resolved_s3 = (
        s3_client
        if s3_client is not None
        else boto3.client("s3", region_name=AWS_REGION)
    )
    smoke_limit = _smoke_limit(smoke)
    progress_rows: list[ProgressRow] = []
    exports = []
    for candidate in _selected_candidates(candidate_id):
        result = export_candidate(
            candidate,
            resolved_run_date,
            resolved_timestamp,
            output_dir,
            resolved_athena,
            resolved_s3,
            smoke_limit=smoke_limit,
        )
        exports.append(result)
        progress_rows.append(
            ProgressRow(
                person=result.display_name,
                query=result.sql,
                total_results=result.row_count,
                s3_path=result.s3_parquet_uri,
            )
        )
        print(format_progress_table(progress_rows))
    compiled = compile_outputs(
        resolved_timestamp,
        resolved_run_date,
        output_dir,
        exports,
        resolved_s3,
    )
    _print_compile_summary(compiled)
    return compiled


def main(argv: list[str] | None = None) -> None:
    """Parse argv and run the export."""

    args = parse_args(argv)
    run(smoke=args.smoke, candidate_id=args.candidate)


if __name__ == "__main__":
    main()
