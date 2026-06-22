"""Upload curated Bluesky data to S3 and delete local dataset files.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/postprocessing/postprocess_bluesky.py \\
        --dataset-id bluesky_<uuid>
"""

from __future__ import annotations

import shutil
from pathlib import Path

import typer

from data_platform.aws.constants import S3_BUCKET
from data_platform.aws.s3 import S3
from data_platform.postprocessing.constants import CURATED_S3_PREFIX
from data_platform.utils.storage import BlueskyStorageManager, StorageStage

app = typer.Typer(add_completion=False)


def postprocess_bluesky(dataset_id: str, curated_path: Path) -> None:
    s3 = S3()
    _upload_curated(s3, dataset_id, curated_path)
    _delete_local(dataset_id)


def _upload_curated(s3: S3, dataset_id: str, curated_path: Path) -> None:
    run_dir = curated_path.parent
    for file in run_dir.iterdir():
        key = f"{CURATED_S3_PREFIX}/platform=bluesky/dataset_id={dataset_id}/{file.name}"
        s3.upload_file(file, S3_BUCKET, key)


def _delete_local(dataset_id: str) -> None:
    dataset_dir = (
        BlueskyStorageManager(StorageStage.RAW, dataset_id).platform_data_root / dataset_id
    )
    shutil.rmtree(dataset_dir)


@app.command()
def main(
    dataset_id: str = typer.Option(
        ...,
        "--dataset-id",
        help="Dataset identifier from ingestion YAML (bluesky_<uuid>)",
    ),
) -> None:
    storage = BlueskyStorageManager(StorageStage.CURATED, dataset_id)
    run_dir = storage.latest_run_dir()
    if run_dir is None:
        raise FileNotFoundError(f"No curated runs found for dataset {dataset_id}")
    curated_path = next(f for f in run_dir.iterdir() if f.name != "metadata.json")
    postprocess_bluesky(dataset_id, curated_path)


if __name__ == "__main__":
    app()
