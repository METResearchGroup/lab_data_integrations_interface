"""Concatenate per-candidate Parquet files and write run metadata."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from experiments.client_request_2026_09_09.constants import (
    CANDIDATES,
    CANDIDATES_BY_ID,
    DATA_START_DATE,
    GLUE_DATABASE,
    GLUE_TABLE,
    IS_CRITICISM_FILTER,
    JSON_INDENT,
    MATCH_RULE,
    METADATA_FILENAME,
    METADATA_NOTES,
    POSTS_PARQUET_FILENAME,
    S3_BUCKET,
    S3_PREFIX,
    SINGLE_CANDIDATE_EXPORT_COUNT,
    UTF8_ENCODING,
    WORKGROUP,
    Candidate,
    metadata_object_key,
    posts_parquet_object_key,
    query_start_date,
    s3_object_uri,
)
from experiments.client_request_2026_09_09.export import CandidateExportResult
from experiments.client_request_2026_09_09.schemas import (
    CandidateMetadataRecord,
    RunMetadata,
    write_combined_parquet,
)


@dataclass(frozen=True)
class CompileResult:
    """Local and S3 paths for the combined Parquet file and metadata."""

    posts_path: Path
    metadata_path: Path
    posts_s3_uri: str
    metadata_s3_uri: str
    total_rows: int


def _exports_by_id(
    exports: list[CandidateExportResult],
) -> dict[str, CandidateExportResult]:
    return {item.candidate_id: item for item in exports}


def _missing_candidate_ids(exports_by_id: dict[str, CandidateExportResult]) -> list[str]:
    return [
        candidate.candidate_id
        for candidate in CANDIDATES
        if candidate.candidate_id not in exports_by_id
    ]


def _require_expected_candidates(exports: list[CandidateExportResult]) -> None:
    if len(exports) == SINGLE_CANDIDATE_EXPORT_COUNT:
        return
    missing = _missing_candidate_ids(_exports_by_id(exports))
    if missing:
        missing_ids = ", ".join(missing)
        raise ValueError(f"Missing candidate export: {missing_ids}")


def _ordered_exports(exports: list[CandidateExportResult]) -> list[CandidateExportResult]:
    exports_by_id = _exports_by_id(exports)
    return [
        exports_by_id[candidate.candidate_id]
        for candidate in CANDIDATES
        if candidate.candidate_id in exports_by_id
    ]


def _candidate_metadata(
    candidate: Candidate,
    export: CandidateExportResult,
    run_date: date,
) -> CandidateMetadataRecord:
    return CandidateMetadataRecord(
        candidate_id=candidate.candidate_id,
        display_name=candidate.display_name,
        primary_date=candidate.primary_date.isoformat(),
        query_start=query_start_date(candidate.primary_date).isoformat(),
        query_end=run_date.isoformat(),
        name_strings=candidate.name_strings,
        row_count=export.row_count,
        s3_parquet_uri=export.s3_parquet_uri,
    )


def _run_metadata(
    run_timestamp: str,
    run_date: date,
    ordered_exports: list[CandidateExportResult],
) -> RunMetadata:
    candidate_records = tuple(
        _candidate_metadata(CANDIDATES_BY_ID[item.candidate_id], item, run_date)
        for item in ordered_exports
    )
    return RunMetadata(
        run_timestamp=run_timestamp,
        glue_database=GLUE_DATABASE,
        glue_table=GLUE_TABLE,
        workgroup=WORKGROUP,
        coverage_start=DATA_START_DATE.isoformat(),
        match_rule=MATCH_RULE,
        is_criticism_filter=IS_CRITICISM_FILTER,
        s3_bucket=S3_BUCKET,
        s3_prefix=S3_PREFIX,
        candidates=candidate_records,
        notes=METADATA_NOTES,
    )


def _concat_export_tables(ordered_exports: list[CandidateExportResult]) -> pa.Table:
    tables = [pq.read_table(item.parquet_path) for item in ordered_exports]
    return pa.concat_tables(tables)


def _write_metadata_json(path: Path, metadata: RunMetadata) -> None:
    payload = asdict(metadata)
    path.write_text(
        json.dumps(payload, indent=JSON_INDENT) + "\n",
        encoding=UTF8_ENCODING,
    )


def compile_outputs(
    run_timestamp: str,
    run_date: date,
    output_dir: Path,
    exports: list[CandidateExportResult],
    s3_client,
) -> CompileResult:
    """Write combined ``posts.parquet`` and ``metadata.json``, then upload both.

    Shared ``uri`` values across candidates are kept. Row counts in metadata
    come from each ``CandidateExportResult``, not from a second file scan.

    A list of exactly one export compiles that subset. Any other list that is
    missing a ``CANDIDATES`` id raises ``ValueError`` naming the missing id.

    Parameters
    ----------
    run_timestamp
        Run folder name under the experiment S3 prefix.
    run_date
        Inclusive UTC end date stored on each candidate as ``query_end``.
    output_dir
        Local directory for ``posts.parquet`` and ``metadata.json``.
    exports
        Per-candidate export results to concatenate.
    s3_client
        S3 client used to upload the two compiled objects.

    Returns
    -------
    CompileResult
        Local paths, S3 URIs, and the sum of export row counts.

    Raises
    ------
    ValueError
        When a multi-candidate ``exports`` list is missing a ``CANDIDATES`` id.
    """

    _require_expected_candidates(exports)
    ordered_exports = _ordered_exports(exports)
    output_dir.mkdir(parents=True, exist_ok=True)
    posts_path = output_dir / POSTS_PARQUET_FILENAME
    metadata_path = output_dir / METADATA_FILENAME
    combined = _concat_export_tables(ordered_exports)
    write_combined_parquet(posts_path, combined)
    metadata = _run_metadata(run_timestamp, run_date, ordered_exports)
    _write_metadata_json(metadata_path, metadata)
    posts_key = posts_parquet_object_key(run_timestamp)
    metadata_key = metadata_object_key(run_timestamp)
    s3_client.upload_file(str(posts_path), S3_BUCKET, posts_key)
    s3_client.upload_file(str(metadata_path), S3_BUCKET, metadata_key)
    total_rows = sum(item.row_count for item in ordered_exports)
    return CompileResult(
        posts_path=posts_path,
        metadata_path=metadata_path,
        posts_s3_uri=s3_object_uri(posts_key),
        metadata_s3_uri=s3_object_uri(metadata_key),
        total_rows=total_rows,
    )
