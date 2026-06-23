"""Curate Twitter posts: join labels, apply business rules, export CSV.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/curate/curate_twitter.py \\
        --dataset-id twitter_<uuid> --config mirrorview.yaml
"""

from __future__ import annotations

from pathlib import Path

import typer

from data_platform.curate.runner import CuratePlatformSpec, run_curation
from data_platform.curate.utils import resolve_curate_config_path
from data_platform.utils.platform_ids import TWITTER_BINDING
from data_platform.utils.storage import TwitterStorageManager

CONFIGS_DIR = Path(__file__).resolve().parent / "configs" / "twitter"

app = typer.Typer(add_completion=False)

TWITTER_CURATE_SPEC = CuratePlatformSpec(
    platform="twitter",
    storage_cls=TwitterStorageManager,
    binding=TWITTER_BINDING,
    record_noun="posts",
)

ID_COLUMN = TWITTER_BINDING.records_id_column
FEATURE_FILE_ID_COLUMN = TWITTER_BINDING.feature_file_id_column


def curate_mirrorview(config_path: Path, dataset_id: str) -> Path:
    return run_curation(config_path, dataset_id, TWITTER_CURATE_SPEC)


@app.command()
def main(
    dataset_id: str = typer.Option(
        ...,
        "--dataset-id",
        help="Dataset identifier from ingestion YAML (twitter_<uuid>)",
    ),
    config: Path = typer.Option(
        Path("mirrorview.yaml"),
        "--config",
        "-c",
        help="Curate config under data_platform/curate/configs/twitter/",
    ),
) -> None:
    config_path = resolve_curate_config_path(config, CONFIGS_DIR)
    curate_mirrorview(config_path, dataset_id)


if __name__ == "__main__":
    app()
