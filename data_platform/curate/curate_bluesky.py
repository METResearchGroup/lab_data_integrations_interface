"""Curate Bluesky posts: join labels, apply business rules, export CSV.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/curate/curate_bluesky.py \\
        --dataset-id bluesky_<uuid> --config mirrorview.yaml
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from data_platform.aws.athena import Athena
from data_platform.aws.constants import S3_BUCKET
from data_platform.aws.s3 import S3
from data_platform.curate.runner import CuratePlatformSpec, run_curation
from data_platform.curate.utils import resolve_curate_config_path
from data_platform.generate_features.metadata import metadata_path
from data_platform.generate_features.models import FeatureRunMetadata
from data_platform.utils.dataset import dataset_root, validate_dataset_id
from data_platform.utils.platform_ids import BLUESKY_BINDING
from data_platform.utils.storage import BlueskyStorageManager, StorageStage

CONFIGS_DIR = Path(__file__).resolve().parent / "configs" / "bluesky"

app = typer.Typer(add_completion=False)

BLUESKY_CURATE_SPEC = CuratePlatformSpec(
    platform="bluesky",
    storage_cls=BlueskyStorageManager,
    binding=BLUESKY_BINDING,
    record_noun="posts",
)


def _publish_curated_run(dataset_id: str, run_dir: Path, output_path: Path) -> None:
    """Upload a curated output file to S3 and register its Athena partition."""
    s3_prefix = f"curated/platform=bluesky/dataset_id={dataset_id}/run_dir={run_dir.name}"
    s3_key = f"{s3_prefix}/{output_path.name}"
    S3().upload_file(output_path, S3_BUCKET, s3_key)
    Athena().register_partition(
        "bluesky_curated",
        {"platform": "bluesky", "dataset_id": dataset_id, "run_dir": run_dir.name},
        f"s3://{S3_BUCKET}/{s3_prefix}/",
    )
    print(f"curate_bluesky: uploaded to s3://{S3_BUCKET}/{s3_key}")
    print(
        f"curate_bluesky: registered partition bluesky_curated"
        f" platform=bluesky dataset_id={dataset_id} run_dir={run_dir.name}"
    )


def _retry_pending_uploads(dataset_id: str, curated_storage: BlueskyStorageManager) -> None:
    """Retry S3 upload for any curated run dirs that completed but failed to upload."""
    if not curated_storage.root_dir.exists():
        return
    for run_dir in sorted(curated_storage.root_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        meta = curated_storage.load_run_metadata(run_dir)
        if meta.get("s3_upload_status", False):
            continue
        output_filename = meta.get("files", {}).get("export")
        if not output_filename:
            continue
        output_path = run_dir / output_filename
        if not output_path.exists():
            continue
        _publish_curated_run(dataset_id, run_dir, output_path)
        meta["s3_upload_status"] = True
        curated_storage.write_run_metadata(run_dir, meta)


def curate(config_path: Path, dataset_id: str) -> Path:
    dataset_id = validate_dataset_id(dataset_id)

    curated_storage = BlueskyStorageManager(StorageStage.CURATED, dataset_id)
    _retry_pending_uploads(dataset_id, curated_storage)

    features_meta_path = metadata_path(dataset_root("bluesky", dataset_id) / "features")
    if not features_meta_path.exists():
        raise FileNotFoundError(f"No features metadata found for dataset {dataset_id}")
    with features_meta_path.open(encoding="utf-8") as f:
        features_meta = FeatureRunMetadata.from_dict(json.load(f))
    if not features_meta.s3_upload_status:
        raise RuntimeError(f"Features for dataset {dataset_id} have not been uploaded to S3")

    preprocessed_storage = BlueskyStorageManager(StorageStage.PREPROCESSED, dataset_id)
    if not preprocessed_storage.all_runs_uploaded():
        raise RuntimeError(
            f"Not all preprocessed runs for dataset {dataset_id} have been uploaded to S3"
        )

    output_path = run_curation(config_path, dataset_id, BLUESKY_CURATE_SPEC)

    run_dir = output_path.parent
    _publish_curated_run(dataset_id, run_dir, output_path)
    curate_meta = curated_storage.load_run_metadata(run_dir)
    curate_meta["s3_upload_status"] = True
    curated_storage.write_run_metadata(run_dir, curate_meta)

    return output_path


@app.command()
def main(
    dataset_id: str = typer.Option(
        ...,
        "--dataset-id",
        help="Dataset identifier from ingestion YAML (bluesky_<uuid>)",
    ),
    config: Path = typer.Option(
        Path("mirrorview.yaml"),
        "--config",
        "-c",
        help="Curate config under data_platform/curate/configs/bluesky/",
    ),
) -> None:
    config_path = resolve_curate_config_path(config, CONFIGS_DIR)
    curate(config_path, dataset_id)


if __name__ == "__main__":
    app()
