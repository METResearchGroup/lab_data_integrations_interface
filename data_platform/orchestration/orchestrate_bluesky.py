"""Orchestrate Bluesky ingestion and preprocessing as a Prefect DAG.

PYTHONPATH=. uv run python data_platform/orchestration/orchestrate_bluesky.py
"""

import os

if __name__ == "__main__":
    os.environ["PREFECT_SERVER_ALLOW_EPHEMERAL_MODE"] = "true"
    os.environ["PREFECT_API_URL"] = ""

from prefect import flow, task

from data_platform.ingestion.sync_bluesky import sync_records
from data_platform.preprocessing.preprocess_bluesky import preprocess_records


@task(name="sync-bluesky")
def sync_task() -> None:
    sync_records()


@task(name="preprocess-bluesky")
def preprocess_task() -> None:
    preprocess_records()


@flow(name="orchestrate-bluesky", log_prints=True)
def orchestrate_bluesky() -> None:
    print("orchestrate_bluesky: starting Bluesky pipeline")
    sync_task()
    preprocess_task()
    print("orchestrate_bluesky: Bluesky pipeline complete")


if __name__ == "__main__":
    orchestrate_bluesky()
