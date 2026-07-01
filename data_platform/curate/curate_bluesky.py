"""Curate Bluesky posts: join labels, apply business rules, export CSV.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/curate/curate_bluesky.py \\
        --dataset-id bluesky_<uuid> --config mirrorview.yaml
"""

from __future__ import annotations

import hashlib
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
from data_platform.utils.dataset import dataset_root, relative_run_path, validate_dataset_id
from data_platform.utils.gate_checks import require_all_runs_uploaded, require_features_uploaded
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


def _is_up_to_date(
    curated_storage: BlueskyStorageManager,
    all_preprocessed_run_dirs: list[Path],
    root: Path,
    rules_hash: str,
) -> Path | None:
    """Return the existing output path if curation inputs haven't changed, else None."""
    if not curated_storage.root_dir.exists():
        return None
    run_dirs = sorted(p for p in curated_storage.root_dir.iterdir() if p.is_dir())
    if not run_dirs:
        return None
    latest_meta = curated_storage.load_run_metadata(run_dirs[-1])
    if not latest_meta.get("s3_upload_status", False):
        return None
    current_runs = [relative_run_path(root, d) for d in all_preprocessed_run_dirs]
    if latest_meta.get("source_preprocessed_runs") != current_runs:
        return None
    if latest_meta.get("rules_hash") != rules_hash:
        return None
    output_filename = latest_meta.get("files", {}).get("export")
    if not output_filename:
        return None
    output_path = run_dirs[-1] / output_filename
    if not output_path.exists():
        return None
    return output_path


def curate(config_path: Path, dataset_id: str) -> Path:
    dataset_id = validate_dataset_id(dataset_id)

    curated_storage = BlueskyStorageManager(StorageStage.CURATED, dataset_id)
    _retry_pending_uploads(dataset_id, curated_storage)

    features_meta_path = metadata_path(dataset_root("bluesky", dataset_id) / "features")
    if not features_meta_path.exists():
        raise FileNotFoundError(f"No features metadata found for dataset {dataset_id}")
    with features_meta_path.open(encoding="utf-8") as f:
        features_meta = FeatureRunMetadata.from_dict(json.load(f))
    require_features_uploaded(features_meta, dataset_id)

    preprocessed_storage = BlueskyStorageManager(StorageStage.PREPROCESSED, dataset_id)
    require_all_runs_uploaded(preprocessed_storage, dataset_id)

    root = dataset_root("bluesky", dataset_id)
    all_preprocessed_run_dirs = sorted(
        p for p in preprocessed_storage.root_dir.iterdir() if p.is_dir()
    )
    rules_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()

    existing = _is_up_to_date(curated_storage, all_preprocessed_run_dirs, root, rules_hash)
    if existing is not None:
        print(f"curate_bluesky: already up to date, skipping ({existing})")
        return existing.parent

    output_path = run_curation(config_path, dataset_id, BLUESKY_CURATE_SPEC, rules_hash=rules_hash)

    run_dir = output_path.parent
    _publish_curated_run(dataset_id, run_dir, output_path)
    curate_meta = curated_storage.load_run_metadata(run_dir)
    curate_meta["s3_upload_status"] = True
    curated_storage.write_run_metadata(run_dir, curate_meta)

    return run_dir


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
