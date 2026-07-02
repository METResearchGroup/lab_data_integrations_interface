"""Orchestrate Bluesky ingestion, preprocessing, feature generation, and curation as a Prefect DAG.

Run mirrorview (default):
    PYTHONPATH=. uv run python data_platform/orchestration/orchestrate_bluesky.py

Run a specific job:
    PYTHONPATH=. uv run python data_platform/orchestration/orchestrate_bluesky.py \\
        --ingestion-config trump_econ_iran.yaml --curate-config trump_econ_iran.yaml
"""

import os

if __name__ == "__main__":
    os.environ["PREFECT_SERVER_ALLOW_EPHEMERAL_MODE"] = "true"
    os.environ["PREFECT_API_URL"] = ""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer
from prefect import flow, task

from data_platform.curate.curate_bluesky import curate as curate_bluesky
from data_platform.curate.utils import resolve_curate_config_path
from data_platform.generate_features.generate_bluesky_features import generate_bluesky_features
from data_platform.ingestion.sync_bluesky import sync_records
from data_platform.ingestion.sync_checkpoint import require_dataset_id
from data_platform.orchestration.pipeline_run import (
    finalize_pipeline_run,
    init_pipeline_run,
    new_pipeline_run_id,
    record_stage_result,
)
from data_platform.preprocessing.preprocess_bluesky import preprocess_records
from data_platform.utils.config_paths import load_yaml_config, resolve_config_path
from lib.timestamp_utils import get_current_timestamp

INGESTION_CONFIGS_DIR = Path(__file__).resolve().parents[1] / "ingestion/configs/bluesky"
CURATE_CONFIGS_DIR = Path(__file__).resolve().parents[1] / "curate/configs/bluesky"

DEFAULT_INGESTION_CONFIG = INGESTION_CONFIGS_DIR / "mirrorview.yaml"
DEFAULT_CURATE_CONFIG = CURATE_CONFIGS_DIR / "mirrorview.yaml"


@task(name="sync-bluesky")
def sync_task(ingestion_config: Path) -> Path:
    return sync_records(ingestion_config)


@task(name="preprocess-bluesky")
def preprocess_task(dataset_id: str) -> Path:
    return preprocess_records(dataset_id)


@task(name="generate-bluesky-features")
def features_task(dataset_id: str) -> dict[str, Path]:
    return generate_bluesky_features(dataset_id)


@task(name="curate-bluesky")
def curate_task(dataset_id: str, curate_config: Path) -> Path:
    return curate_bluesky(curate_config, dataset_id)


def _run_stage(
    pipeline_run_id: str,
    stage_name: str,
    fn: Callable[[], Any],
    run_id_from_result: Callable[[Any], str | None],
) -> Any:
    """Run one stage, then record its result in the pipeline run record.

    On failure, marks the stage and the overall pipeline as failed and re-raises so the
    Prefect flow run stops immediately -- no retry within this invocation. Recovery is
    left to the next orchestrator invocation."""
    try:
        result = fn()
    except Exception as e:
        record_stage_result(pipeline_run_id, stage_name, run_id=None, status="failed", error=str(e))
        finalize_pipeline_run(
            pipeline_run_id, status="failed", completed_at=get_current_timestamp()
        )
        raise
    record_stage_result(
        pipeline_run_id, stage_name, run_id=run_id_from_result(result), status="completed"
    )
    return result


@flow(name="orchestrate-bluesky", log_prints=True)
def orchestrate_bluesky(
    ingestion_config: Path = DEFAULT_INGESTION_CONFIG,
    curate_config: Path = DEFAULT_CURATE_CONFIG,
) -> None:
    config = load_yaml_config(resolve_config_path(ingestion_config, INGESTION_CONFIGS_DIR))
    dataset_id = require_dataset_id(config, platform="bluesky")

    pipeline_run_id = new_pipeline_run_id()
    init_pipeline_run(pipeline_run_id, dataset_id, get_current_timestamp())

    print(f"orchestrate_bluesky: starting pipeline {pipeline_run_id} for dataset {dataset_id}")
    _run_stage(pipeline_run_id, "ingestion", lambda: sync_task(ingestion_config), lambda r: r.name)
    _run_stage(
        pipeline_run_id,
        "preprocessing",
        lambda: preprocess_task(dataset_id),
        lambda r: r.name,
    )
    _run_stage(pipeline_run_id, "features", lambda: features_task(dataset_id), lambda _: None)
    _run_stage(
        pipeline_run_id,
        "curation",
        lambda: curate_task(dataset_id, curate_config),
        lambda r: r.name,
    )

    finalize_pipeline_run(pipeline_run_id, status="completed", completed_at=get_current_timestamp())
    print(f"orchestrate_bluesky: pipeline {pipeline_run_id} complete for dataset {dataset_id}")


def main(
    ingestion_config: Path = typer.Option(
        DEFAULT_INGESTION_CONFIG,
        "--ingestion-config",
        help="Ingestion YAML filename under ingestion/configs/bluesky/ (e.g. trump_econ_iran.yaml)",
    ),
    curate_config: Path = typer.Option(
        DEFAULT_CURATE_CONFIG,
        "--curate-config",
        help="Curate YAML filename under curate/configs/bluesky/ (e.g. trump_econ_iran.yaml)",
    ),
) -> None:
    ingestion_config = resolve_config_path(ingestion_config, INGESTION_CONFIGS_DIR)
    curate_config = resolve_curate_config_path(curate_config, CURATE_CONFIGS_DIR)
    orchestrate_bluesky(ingestion_config, curate_config)


if __name__ == "__main__":
    typer.run(main)
