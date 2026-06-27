"""Curate Reddit comments: join labels, apply business rules, export CSV.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/curate/curate_reddit.py \\
        --dataset-id reddit_<uuid> --config mirrorview.yaml
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import typer

from data_platform.curate.runner import CuratePlatformSpec, run_curation
from data_platform.curate.utils import resolve_curate_config_path
from data_platform.utils.platform_ids import REDDIT_BINDING
from data_platform.utils.storage import RedditStorageManager

CONFIGS_DIR = Path(__file__).resolve().parent / "configs" / "reddit"

app = typer.Typer(add_completion=False)

REDDIT_CURATE_SPEC = CuratePlatformSpec(
    platform="reddit",
    storage_cls=RedditStorageManager,
    binding=REDDIT_BINDING,
    record_noun="comments",
)

ID_COLUMN = REDDIT_BINDING.records_id_column
FEATURE_FILE_ID_COLUMN = REDDIT_BINDING.feature_file_id_column


def curate(config_path: Path, dataset_id: str) -> Path:
    rules_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()
    return run_curation(config_path, dataset_id, REDDIT_CURATE_SPEC, rules_hash=rules_hash)


@app.command()
def main(
    dataset_id: str = typer.Option(
        ...,
        "--dataset-id",
        help="Dataset identifier from ingestion YAML (reddit_<uuid>)",
    ),
    config: Path = typer.Option(
        Path("mirrorview.yaml"),
        "--config",
        "-c",
        help="Curate config under data_platform/curate/configs/reddit/",
    ),
) -> None:
    config_path = resolve_curate_config_path(config, CONFIGS_DIR)
    curate(config_path, dataset_id)


if __name__ == "__main__":
    app()
