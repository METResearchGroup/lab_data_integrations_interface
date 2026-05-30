"""Curate Bluesky posts: join labels, apply business rules, export CSV.

Run from the repo root:

    PYTHONPATH=. uv run python data_platform/curate/curate_bluesky.py --dataset-id bluesky_<uuid> --config mirrorview.yaml
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from data_platform.curate.apply_rules import apply_rules, load_rules_config
from data_platform.curate.consolidate import ConsolidateConfig, build_wide_table
from data_platform.utils.dataset import dataset_root, relative_run_path, validate_dataset_id
from data_platform.utils.storage import BlueskyStorageManager
from lib.timestamp_utils import get_current_timestamp

CONFIGS_DIR = Path(__file__).resolve().parent / "configs" / "bluesky"

app = typer.Typer(add_completion=False)


def resolve_config_path(config: Path) -> Path:
    candidates = [config]
    if config.suffix != ".yaml":
        candidates.append(config.with_suffix(".yaml"))
    if config.parent == Path("."):
        candidates.extend(
            CONFIGS_DIR / candidate.name for candidate in list(candidates)
        )

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    raise FileNotFoundError(f"Config not found: {config}")


def curate_mirrorview(config_path: Path, dataset_id: str) -> Path:
    dataset_id = validate_dataset_id(dataset_id)
    root = dataset_root("bluesky", dataset_id)
    preprocessed_storage = BlueskyStorageManager("preprocessed", dataset_id)
    curated_storage = BlueskyStorageManager("curated", dataset_id)
    features_root = root / "features"

    rules = load_rules_config(config_path)
    preprocessed_run = preprocessed_storage.latest_run_dir()
    if preprocessed_run is None:
        raise FileNotFoundError(
            f"No preprocessed runs found for dataset {dataset_id}"
        )

    posts_csv = preprocessed_run / preprocessed_storage.records_filename
    wide_df = build_wide_table(
        ConsolidateConfig(posts_csv=posts_csv, features_root=features_root)
    )
    rules_result = apply_rules(wide_df, rules)
    filtered_df = rules_result.dataframe

    run_dir = curated_storage.create_new_run_dir(get_current_timestamp())
    output_path = run_dir / rules.output.filename
    filtered_df.to_csv(output_path, index=False)

    metadata: dict[str, Any] = {
        "dataset_id": dataset_id,
        "name": rules.name,
        "source_preprocessed_run": relative_run_path(root, preprocessed_run),
        "row_counts": {
            "preprocessed": len(wide_df),
            "wide": len(wide_df),
            "after_filters": len(filtered_df),
        },
        "filter_results": [
            {
                **step.rule.model_dump(),
                "records_before": step.records_before,
                "records_passing": step.records_passing,
            }
            for step in rules_result.steps
        ],
        "files": {"export": rules.output.filename},
    }
    curated_storage.write_run_metadata(run_dir, metadata)

    print(
        f"curate_mirrorview: kept {len(filtered_df)} of {len(wide_df)} posts -> {run_dir}"
    )
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
    config_path = resolve_config_path(config)
    curate_mirrorview(config_path, dataset_id)


if __name__ == "__main__":
    app()
