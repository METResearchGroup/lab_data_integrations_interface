"""Shared curation pipeline for platform entrypoints."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from data_platform.curate.apply_rules import ApplyRulesResult, apply_rules, load_rules_config
from data_platform.curate.consolidate import ConsolidateConfig, build_wide_table
from data_platform.utils.dataset import dataset_root, relative_run_path, validate_dataset_id
from data_platform.utils.platform_ids import PlatformIdBinding
from data_platform.utils.storage import StorageManager
from lib.timestamp_utils import get_current_timestamp

StorageManagerFactory = Callable[..., StorageManager]


@dataclass(frozen=True)
class CuratePlatformSpec:
    platform: str
    storage_cls: StorageManagerFactory
    binding: PlatformIdBinding
    record_noun: str


def build_curate_metadata(
    *,
    dataset_id: str,
    rules_name: str,
    source_preprocessed_runs: list[str],
    wide_df: pd.DataFrame,
    filtered_df: pd.DataFrame,
    rules_result: ApplyRulesResult,
    export_filename: str,
) -> dict[str, Any]:
    return {
        "dataset_id": dataset_id,
        "name": rules_name,
        "source_preprocessed_runs": source_preprocessed_runs,
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
        "files": {"export": export_filename},
    }


def run_curation(config_path: Path, dataset_id: str, spec: CuratePlatformSpec) -> Path:
    dataset_id = validate_dataset_id(dataset_id)
    root = dataset_root(spec.platform, dataset_id)
    preprocessed_storage = spec.storage_cls("preprocessed", dataset_id)
    curated_storage = spec.storage_cls("curated", dataset_id)
    features_root = root / "features"

    rules = load_rules_config(config_path)
    if not preprocessed_storage.root_dir.exists():
        raise FileNotFoundError(f"No preprocessed runs found for dataset {dataset_id}")
    all_run_dirs = sorted(p for p in preprocessed_storage.root_dir.iterdir() if p.is_dir())
    if not all_run_dirs:
        raise FileNotFoundError(f"No preprocessed runs found for dataset {dataset_id}")

    posts_glob = preprocessed_storage.root_dir / "*" / preprocessed_storage.records_filename
    consolidate_kwargs: dict[str, Any] = {
        "posts_file": posts_glob,
        "features_root": features_root,
    }
    if spec.binding.records_id_column != "uri":
        consolidate_kwargs["id_column"] = spec.binding.records_id_column
        consolidate_kwargs["feature_file_id_column"] = spec.binding.feature_file_id_column

    wide_df = build_wide_table(ConsolidateConfig(**consolidate_kwargs))
    rules_result = apply_rules(wide_df, rules)
    filtered_df = rules_result.dataframe

    run_dir = curated_storage.create_new_run_dir(get_current_timestamp())
    output_filename = curated_storage.filename_for(rules.output.stem)
    output_path = curated_storage.write_dataframe(filtered_df, run_dir, filename=output_filename)

    source_preprocessed_runs = [relative_run_path(root, d) for d in all_run_dirs]
    metadata = build_curate_metadata(
        dataset_id=dataset_id,
        rules_name=rules.name,
        source_preprocessed_runs=source_preprocessed_runs,
        wide_df=wide_df,
        filtered_df=filtered_df,
        rules_result=rules_result,
        export_filename=output_filename,
    )
    curated_storage.write_run_metadata(run_dir, metadata)

    print(
        f"curate_mirrorview: kept {len(filtered_df)} of {len(wide_df)} "
        f"{spec.record_noun} -> {run_dir}"
    )
    return output_path
