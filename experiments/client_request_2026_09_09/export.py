"""Export one candidate's name-match posts through Athena UNLOAD."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from experiments.client_request_2026_09_09.constants import (
    GLUE_DATABASE,
    S3_BUCKET,
    WORKGROUP,
    Candidate,
    candidate_parquet_object_key,
    s3_object_uri,
    unload_object_prefix,
)
from experiments.client_request_2026_09_09.s3_export import (
    download_s3_prefix,
    merge_parquet_files,
)
from experiments.client_request_2026_09_09.schemas import (
    empty_combined_table,
    write_combined_parquet,
)
from experiments.client_request_2026_09_09.sql import build_unload_sql
from lib.aws.athena import Athena

UNLOAD_DOWNLOAD_PREFIX = "candidate-unload-"


@dataclass(frozen=True)
class CandidateExportResult:
    """Local and S3 artifacts from one candidate UNLOAD."""

    candidate_id: str
    display_name: str
    sql: str
    parquet_path: Path
    s3_parquet_uri: str
    row_count: int


def _write_merged_or_empty_parquet(
    s3_client,
    unload_prefix: str,
    parquet_path: Path,
) -> int:
    with tempfile.TemporaryDirectory(prefix=UNLOAD_DOWNLOAD_PREFIX) as tmp_dir:
        downloaded = download_s3_prefix(
            s3_client,
            S3_BUCKET,
            unload_prefix,
            Path(tmp_dir),
        )
        if not downloaded:
            write_combined_parquet(parquet_path, empty_combined_table())
            return 0
        return merge_parquet_files(downloaded, parquet_path)


def export_candidate(
    candidate: Candidate,
    run_date: date,
    run_timestamp: str,
    output_dir: Path,
    athena: Athena,
    s3_client,
    smoke_limit: int | None = None,
) -> CandidateExportResult:
    """UNLOAD, merge, and upload one candidate's Parquet file.

    A successful query that produces no S3 parts writes an empty Parquet file
    with the combined schema, uploads it, and returns ``row_count`` 0. Athena
    ``RuntimeError`` is not caught.

    Parameters
    ----------
    candidate
        Person to export.
    run_date
        Inclusive UTC end date passed to the SQL builder.
    run_timestamp
        Run folder name under the experiment S3 prefix.
    output_dir
        Local directory for ``<candidate_id>.parquet``.
    athena
        Query client. Tests inject a fake with ``run_query``.
    s3_client
        S3 client used to download UNLOAD parts and upload the merge.
    smoke_limit
        Optional inner ``LIMIT`` forwarded to the SQL builder.

    Returns
    -------
    CandidateExportResult
        SQL that ran, local path, merged S3 URI, and merged row count.
    """

    unload_prefix = unload_object_prefix(run_timestamp, candidate.candidate_id)
    unload_uri = s3_object_uri(unload_prefix)
    merged_key = candidate_parquet_object_key(run_timestamp, candidate.candidate_id)
    merged_uri = s3_object_uri(merged_key)
    sql = build_unload_sql(
        candidate,
        run_date=run_date,
        s3_uri=unload_uri,
        smoke_limit=smoke_limit,
    )
    athena.run_query(sql, database=GLUE_DATABASE, workgroup=WORKGROUP)
    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / f"{candidate.candidate_id}.parquet"
    row_count = _write_merged_or_empty_parquet(s3_client, unload_prefix, parquet_path)
    s3_client.upload_file(str(parquet_path), S3_BUCKET, merged_key)
    return CandidateExportResult(
        candidate_id=candidate.candidate_id,
        display_name=candidate.display_name,
        sql=sql,
        parquet_path=parquet_path,
        s3_parquet_uri=merged_uri,
        row_count=row_count,
    )
