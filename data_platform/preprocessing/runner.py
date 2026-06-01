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
from data_platform.utils.storage import StorageManager

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


def load_raw_records(spec: PreprocessPlatformSpec, dataset_id: str) -> pd.DataFrame:
    """Load raw records for preprocessing from the latest sync run."""
    raw_storage = spec.storage_cls("raw", dataset_id)
    records = raw_storage.load_records(latest=True)
    if records.empty:
        return records.copy()

    return pd.DataFrame(_rows_to_validated_dicts(records.to_dict(orient="records"), spec.model_cls))


def save_preprocessed(
    records: pd.DataFrame,
    spec: PreprocessPlatformSpec,
    dataset_id: str,
    input_count: int,
) -> Path:
    """Persist preprocessed records to a new timestamped run directory."""
    raw_storage = spec.storage_cls("raw", dataset_id)
    preprocessed_storage = spec.storage_cls("preprocessed", dataset_id)
    root = dataset_root(spec.platform, dataset_id)

    output_dir = preprocessed_storage.create_new_run_dir()
    preprocessed_storage.write_records(records.to_dict(orient="records"), output_dir)
    source_raw_run = raw_storage.latest_run_dir()
    metadata: dict[str, Any] = {
        "dataset_id": dataset_id,
        "source_raw_run": (
            relative_run_path(root, source_raw_run) if source_raw_run is not None else None
        ),
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


def preprocess_records(dataset_id: str, spec: PreprocessPlatformSpec) -> Path:
    dataset_id = validate_dataset_id(dataset_id)
    records = load_raw_records(spec, dataset_id)
    preprocessed = filter_records(records, spec)
    output_dir = save_preprocessed(preprocessed, spec, dataset_id, input_count=len(records))
    noun = spec.binding.records_file_key
    print(f"preprocess_records: kept {len(preprocessed)} of {len(records)} {noun} -> {output_dir}")
    return output_dir
