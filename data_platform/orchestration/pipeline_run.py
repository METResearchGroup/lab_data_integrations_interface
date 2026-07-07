"""Pipeline run records: which orchestrator invocation triggered which stage executions.

Distinct from stage-level data lineage (`source_*_runs` in each stage's metadata.json,
already tracked there). See strategy_planning/2026-06-29_pipeline_run_metadata.md.
"""

from __future__ import annotations

import uuid
from typing import Any

from data_platform.aws.constants import PIPELINE_RUNS_TABLE
from data_platform.aws.dynamodb import DynamoDB

STAGE_NAMES = ("ingestion", "preprocessing", "features", "curation", "disk_cleanup")


def new_pipeline_run_id() -> str:
    return str(uuid.uuid4())


def init_pipeline_run(pipeline_run_id: str, dataset_id: str, started_at: str) -> None:
    """Write the initial record for a pipeline run, before any stage has executed."""
    item: dict[str, Any] = {
        "pipeline_run_id": pipeline_run_id,
        "dataset_id": dataset_id,
        "started_at": started_at,
        "status": "in_progress",
        "stages": {stage: {"run_id": None, "status": "not_started"} for stage in STAGE_NAMES},
    }
    DynamoDB().put_item(PIPELINE_RUNS_TABLE, item)


def record_stage_result(
    pipeline_run_id: str,
    stage: str,
    *,
    run_id: str | None,
    status: str,
    error: str | None = None,
) -> None:
    """Update a single stage's entry, leaving the other stages' entries untouched."""
    if stage not in STAGE_NAMES:
        raise ValueError(f"Unknown stage {stage!r}, expected one of {STAGE_NAMES}")
    stage_entry: dict[str, Any] = {"run_id": run_id, "status": status}
    if error is not None:
        stage_entry["error"] = error
    DynamoDB().update_item(
        PIPELINE_RUNS_TABLE,
        key={"pipeline_run_id": pipeline_run_id},
        updates={f"stages.{stage}": stage_entry},
    )


def finalize_pipeline_run(pipeline_run_id: str, *, status: str, completed_at: str) -> None:
    DynamoDB().update_item(
        PIPELINE_RUNS_TABLE,
        key={"pipeline_run_id": pipeline_run_id},
        updates={"status": status, "completed_at": completed_at},
    )
