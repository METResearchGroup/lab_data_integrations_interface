from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from data_platform.utils.storage import StorageManager


class DedupePolicy(StrEnum):
    CURRENT_RUN = "current_run"
    PRIOR_RUNS_SAME_DATASET = "prior_runs_same_dataset"
    PRIOR_RUNS_ALL_DATASETS = "prior_runs_all_datasets"


def parse_policies(raw: list[str]) -> list[DedupePolicy]:
    if not raw:
        raise ValueError("dedupe policy must be a non-empty list")
    policies = [DedupePolicy(value) for value in raw]
    if DedupePolicy.CURRENT_RUN not in policies:
        raise ValueError("dedupe policy must include current_run")
    if (
        DedupePolicy.PRIOR_RUNS_SAME_DATASET in policies
        and DedupePolicy.PRIOR_RUNS_ALL_DATASETS in policies
    ):
        raise ValueError(
            "dedupe policy cannot include both prior_runs_same_dataset and prior_runs_all_datasets"
        )
    return policies


@dataclass(frozen=True)
class DedupeConfig:
    policies: list[DedupePolicy]
    id_column: str
    filename: str | None = None

    @classmethod
    def from_ingestion_params(
        cls,
        ingestion_params: dict[str, Any],
        id_column: str,
        *,
        filename: str | None = None,
        policy_key: str = "dedupe_policy",
    ) -> DedupeConfig:
        raw = ingestion_params[policy_key]
        if not isinstance(raw, list):
            raise ValueError(f"{policy_key} must be a list")
        return cls(
            policies=parse_policies([str(value) for value in raw]),
            id_column=id_column,
            filename=filename,
        )


@dataclass
class DedupeSession:
    config: DedupeConfig
    seen_ids: set[str]

    def __init__(self, config: DedupeConfig) -> None:
        self.config = config
        self.seen_ids: set[str] = set()

    def warm(self, storage: StorageManager, output_dir: Path) -> None:  # noqa: F821
        seen: set[str] = set()
        for policy in self.config.policies:
            if policy is DedupePolicy.CURRENT_RUN:
                seen.update(
                    storage.load_seen_ids(
                        output_dir,
                        self.config.id_column,
                        filename=self.config.filename,
                    )
                )
            elif policy is DedupePolicy.PRIOR_RUNS_SAME_DATASET:
                seen.update(
                    storage.load_seen_ids_from_prior_runs(
                        output_dir,
                        self.config.id_column,
                        filename=self.config.filename,
                    )
                )
            elif policy is DedupePolicy.PRIOR_RUNS_ALL_DATASETS:
                seen.update(
                    storage.load_seen_ids_from_platform_raw_runs(
                        output_dir,
                        self.config.id_column,
                        filename=self.config.filename,
                    )
                )
        self.seen_ids = seen

    def filter_rows(self, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        new_rows = [row for row in rows if row[self.config.id_column] not in self.seen_ids]
        skipped = len(rows) - len(new_rows)
        return new_rows, skipped

    def note_appended(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self.seen_ids.add(row[self.config.id_column])


@dataclass(frozen=True)
class DedupeResult:
    kept: int
    skipped: int
