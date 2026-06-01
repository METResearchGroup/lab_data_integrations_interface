"""Orchestrate Bluesky ingestion and preprocessing as a Prefect DAG.

PYTHONPATH=. uv run python data_platform/orchestration/orchestrate_bluesky.py
"""

import os

if __name__ == "__main__":
    os.environ["PREFECT_SERVER_ALLOW_EPHEMERAL_MODE"] = "true"
    os.environ["PREFECT_API_URL"] = ""

from pathlib import Path

from prefect import flow, task

from data_platform.ingestion.sync_bluesky import _require_dataset_id, sync_records
from data_platform.utils.config_paths import load_yaml_config, resolve_config_path
from data_platform.preprocessing.preprocess_bluesky import preprocess_records

MIRRORVIEW_CONFIG = (
    Path(__file__).resolve().parents[1] / "ingestion/configs/bluesky/mirrorview.yaml"
)


@task(name="sync-bluesky")
def sync_task() -> None:
    sync_records()


@task(name="preprocess-bluesky")
def preprocess_task() -> None:
    config = load_yaml_config(resolve_config_path(MIRRORVIEW_CONFIG, MIRRORVIEW_CONFIG.parent))
    preprocess_records(_require_dataset_id(config))


@flow(name="orchestrate-bluesky", log_prints=True)
def orchestrate_bluesky() -> None:
    print("orchestrate_bluesky: starting Bluesky pipeline")
    sync_task()
    preprocess_task()
    print("orchestrate_bluesky: Bluesky pipeline complete")


if __name__ == "__main__":
    orchestrate_bluesky()
