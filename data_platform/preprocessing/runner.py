"""Shared preprocessing pipeline for platform entrypoints."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel

from data_platform.utils.dataset import dataset_root, relative_run_path, validate_dataset_id
from data_platform.utils.platform_ids import PlatformIdBinding
from data_platform.utils.storage import StorageManager, StorageStage

TextValidator = Callable[[str], bool]
RowValidator = Callable[[str], bool]

StorageManagerFactory = Callable[..., StorageManager]

AUTHOR_COLUMN = "author"


@dataclass(frozen=True)
class PreprocessPlatformSpec:
    platform: str
    storage_cls: StorageManagerFactory
    model_cls: type[BaseModel]
    binding: PlatformIdBinding
    text_validators: tuple[TextValidator, ...]
    row_validators: tuple[RowValidator, ...] = ()
    text_transform: Callable[[str], str] | None = None


def apply_text_transform(
    df: pd.DataFrame,
    spec: PreprocessPlatformSpec,
) -> pd.DataFrame:
    if spec.text_transform is None or df.empty:
        return df
    out = df.copy()
    text_col = spec.binding.text_column
    transform = spec.text_transform
    out[text_col] = out[text_col].map(lambda v: transform(str(v)))
    return out


def passes_all_validators(
    text: str,
    validators: Sequence[TextValidator],
) -> bool:
    return all(validator(text) for validator in validators)


def passes_row_validators(
    author: str,
    validators: Sequence[RowValidator],
) -> bool:
    return all(validator(author) for validator in validators)


def filter_records(df: pd.DataFrame, spec: PreprocessPlatformSpec) -> pd.DataFrame:
    """Return only rows whose text (and optional author) pass every validator."""
    if df.empty:
        return df.copy()

    text_col = spec.binding.text_column
    text_mask = df[text_col].map(
        lambda value: passes_all_validators(str(value), spec.text_validators)
    )
    if not spec.row_validators:
        return df.loc[text_mask].reset_index(drop=True)

    author_mask = df[AUTHOR_COLUMN].map(
        lambda value: passes_row_validators(str(value), spec.row_validators)
    )
    return df.loc[text_mask & author_mask].reset_index(drop=True)


def _rows_to_validated_dicts(
    rows: list[dict[str, Any]],
    model_cls: type[BaseModel],
) -> list[dict[str, Any]]:
    return [model_cls.model_validate(row).model_dump() for row in rows]


def load_raw_records(
    spec: PreprocessPlatformSpec,
    dataset_id: str,
    *,
    latest_only: bool,
) -> tuple[pd.DataFrame, list[Path]]:
    """Load raw records for preprocessing.

    Returns both the loaded/validated records and the raw run directories they came from.
    """
    raw_storage = spec.storage_cls(StorageStage.RAW, dataset_id)
    if latest_only:
        records = raw_storage.load_records(latest=True)
        if records.empty:
            return records.copy(), []

        source_dir = raw_storage.latest_run_dir()
        source_raw_run_dirs = [source_dir] if source_dir is not None else []

        validated = _rows_to_validated_dicts(records.to_dict(orient="records"), spec.model_cls)
        return pd.DataFrame(validated), source_raw_run_dirs

    raw_root = raw_storage.root_dir
    run_dirs = sorted([p for p in raw_root.iterdir() if p.is_dir()])
    validated_rows: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        df = raw_storage.load_records(run_dir=run_dir)
        if df.empty:
            continue
        validated_rows.extend(
            _rows_to_validated_dicts(df.to_dict(orient="records"), spec.model_cls)
        )

    records = (
        pd.DataFrame(validated_rows)
        if validated_rows
        else pd.DataFrame(columns=list(spec.model_cls.model_fields.keys()))
    )
    return records, run_dirs


def save_preprocessed(
    records: pd.DataFrame,
    spec: PreprocessPlatformSpec,
    dataset_id: str,
    input_count: int,
    *,
    source_raw_run_dirs: list[Path],
) -> Path:
    """Persist preprocessed records to a new timestamped run directory."""
    preprocessed_storage = spec.storage_cls(StorageStage.PREPROCESSED, dataset_id)
    root = dataset_root(spec.platform, dataset_id)

    output_dir = preprocessed_storage.create_new_run_dir()
    preprocessed_storage.write_records(records.to_dict(orient="records"), output_dir)
    source_raw_runs = [relative_run_path(root, d) for d in source_raw_run_dirs]
    source_raw_run = source_raw_runs[-1] if source_raw_runs else None
    metadata: dict[str, Any] = {
        "dataset_id": dataset_id,
        "source_raw_run": (source_raw_run),
        "source_raw_runs": source_raw_runs,
        "preprocess_timestamp": output_dir.name,
        "row_counts": {
            "input": input_count,
            "output": len(records),
        },
        "files": {
            spec.binding.records_file_key: preprocessed_storage.records_filename,
        },
    }
    preprocessed_storage.write_run_metadata(output_dir, metadata)
    return output_dir


def preprocess_records(
    dataset_id: str,
    spec: PreprocessPlatformSpec,
    *,
    latest_only: bool = True,
) -> Path:
    dataset_id = validate_dataset_id(dataset_id)
    raw_storage = spec.storage_cls(StorageStage.RAW, dataset_id)
    latest_raw_run = raw_storage.latest_run_dir()
    if latest_raw_run is None:
        raise FileNotFoundError(f"No raw runs found for dataset {dataset_id}")
    raw_metadata = raw_storage.load_run_metadata(latest_raw_run)
    if raw_metadata.get("sync_status") != "completed":
        raise RuntimeError(
            f"Latest raw run {latest_raw_run.name} is not completed "
            f"(status={raw_metadata.get('sync_status')})"
        )
    records, source_raw_run_dirs = load_raw_records(spec, dataset_id, latest_only=latest_only)
    if not latest_only and not records.empty:
        id_col = spec.binding.records_id_column
        # Newest wins: run-dir directories are concatenated in ascending name order,
        # then drop_duplicates keep="last".
        records = records.drop_duplicates(subset=[id_col], keep="last").reset_index(drop=True)

    preprocessed = filter_records(records, spec)
    preprocessed = apply_text_transform(preprocessed, spec)
    output_dir = save_preprocessed(
        preprocessed,
        spec,
        dataset_id,
        input_count=len(records),
        source_raw_run_dirs=source_raw_run_dirs,
    )
    noun = spec.binding.records_file_key
    print(f"preprocess_records: kept {len(preprocessed)} of {len(records)} {noun} -> {output_dir}")
    return output_dir
