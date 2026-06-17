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

from pathlib import Path

import typer
from prefect import flow, task

from data_platform.curate.curate_bluesky import curate_mirrorview
from data_platform.curate.utils import resolve_curate_config_path
from data_platform.generate_features.generate_bluesky_features import generate_bluesky_features
from data_platform.ingestion.sync_bluesky import sync_records
from data_platform.ingestion.sync_checkpoint import require_dataset_id
from data_platform.preprocessing.preprocess_bluesky import preprocess_records
from data_platform.utils.config_paths import load_yaml_config, resolve_config_path

INGESTION_CONFIGS_DIR = Path(__file__).resolve().parents[1] / "ingestion/configs/bluesky"
CURATE_CONFIGS_DIR = Path(__file__).resolve().parents[1] / "curate/configs/bluesky"

DEFAULT_INGESTION_CONFIG = INGESTION_CONFIGS_DIR / "mirrorview.yaml"
DEFAULT_CURATE_CONFIG = CURATE_CONFIGS_DIR / "mirrorview.yaml"


@task(name="sync-bluesky")
def sync_task(ingestion_config: Path) -> None:
    sync_records(ingestion_config)


@task(name="preprocess-bluesky")
def preprocess_task(dataset_id: str) -> None:
    preprocess_records(dataset_id)


@task(name="generate-bluesky-features")
def features_task(dataset_id: str) -> None:
    generate_bluesky_features(dataset_id)


@task(name="curate-bluesky")
def curate_task(dataset_id: str, curate_config: Path) -> None:
    curate_mirrorview(curate_config, dataset_id)


@flow(name="orchestrate-bluesky", log_prints=True)
def orchestrate_bluesky(
    ingestion_config: Path = DEFAULT_INGESTION_CONFIG,
    curate_config: Path = DEFAULT_CURATE_CONFIG,
) -> None:
    config = load_yaml_config(resolve_config_path(ingestion_config, INGESTION_CONFIGS_DIR))
    dataset_id = require_dataset_id(config, platform="bluesky")

    print(f"orchestrate_bluesky: starting pipeline for dataset {dataset_id}")
    sync_task(ingestion_config)
    preprocess_task(dataset_id)
    features_task(dataset_id)
    curate_task(dataset_id, curate_config)
    print(f"orchestrate_bluesky: pipeline complete for dataset {dataset_id}")


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
