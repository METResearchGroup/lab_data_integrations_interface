from __future__ import annotations

from pathlib import Path

import typer

from experiments.reddit_data_dump_labeling_2026_06_16.patch_data_root import patch_data_root

patch_data_root()

from data_platform.curate.curate_reddit import REDDIT_CURATE_SPEC, curate_mirrorview
from experiments.reddit_data_dump_labeling_2026_06_16.paths import EXPERIMENT_ROOT, dataset_id_for

CURATE_CONFIG_PATH = EXPERIMENT_ROOT / "configs" / "mirrorview.yaml"


def run_curate(
    batch: str,
    *,
    config_path: Path | None = None,
    data_root: Path | None = None,
) -> Path:
    if data_root is not None:
        patch_data_root(data_root)

    dataset_id = dataset_id_for(batch)
    config = config_path or CURATE_CONFIG_PATH
    if not config.exists():
        raise FileNotFoundError(f"Curate config not found: {config}")
    return curate_mirrorview(config, dataset_id)


def main(
    batch: str = typer.Option(..., "--batch", help="Batch key from batches.yaml"),
) -> None:
    output_path = run_curate(batch)
    print(f"run_curate: wrote {output_path}")


if __name__ == "__main__":
    typer.run(main)
