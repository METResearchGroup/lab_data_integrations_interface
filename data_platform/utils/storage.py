from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel

from data_platform.models.sync import (
    SyncBlueskyPostModel,
    SyncRedditCommentModel,
    SyncRedditPostModel,
    SyncTwitterPostModel,
)
from data_platform.utils.dataset import ValidDataFormats, load_dataset_format, validate_dataset_id
from data_platform.utils.deduplication import DedupeSession
from lib.timestamp_utils import get_current_timestamp

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
METADATA_FILENAME = "metadata.json"


@dataclass(frozen=True)
class AppendResult:
    kept: int
    skipped: int


class StorageStage(StrEnum):
    RAW = "raw"
    PREPROCESSED = "preprocessed"
    FEATURES = "features"
    CURATED = "curated"


def _write_csv(rows: list[dict[str, Any]], output_path: Path, fieldnames: list[str]) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _append_csv(rows: list[dict[str, Any]], output_path: Path, fieldnames: list[str]) -> None:
    file_exists = output_path.exists()
    mode = "a" if file_exists else "w"
    with output_path.open(mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


class StorageManager:
    platform: str
    stage: StorageStage
    model: type[BaseModel]
    records_filename: str
    dataset_id: str

    def __init__(
        self,
        platform: str,
        stage: StorageStage,
        model: type[BaseModel],
        dataset_id: str,
        *,
        records_filename: str,
    ) -> None:
        self.platform = platform
        self.stage = stage
        self.model = model
        self.dataset_id = validate_dataset_id(dataset_id)
        self.format: ValidDataFormats = load_dataset_format(platform, dataset_id)
        stem = Path(records_filename).stem
        self.records_filename = f"{stem}.{self.format.value}"

    @property
    def platform_data_root(self) -> Path:
        return DATA_ROOT / self.platform

    @property
    def root_dir(self) -> Path:
        return DATA_ROOT / self.platform / self.dataset_id / self.stage

    def create_new_run_dir(self, timestamp: str | None = None) -> Path:
        run_dir = self.root_dir / (timestamp or get_current_timestamp())
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def latest_run_dir(self) -> Path | None:
        if not self.root_dir.exists():
            return None
        run_dirs = [path for path in self.root_dir.iterdir() if path.is_dir()]
        if not run_dirs:
            return None
        return max(run_dirs, key=lambda path: path.name)

    def _resolve_run_dir(
        self,
        run_dir: Path | None,
        *,
        latest: bool,
    ) -> Path:
        if run_dir is not None:
            return run_dir
        if latest:
            resolved = self.latest_run_dir()
            if resolved is None:
                raise FileNotFoundError(f"No {self.stage} runs found under {self.root_dir}")
            return resolved
        raise ValueError("Either run_dir must be provided or latest=True")

    def write_records(
        self,
        rows: list[dict[str, Any]],
        run_dir: Path,
        *,
        filename: str | None = None,
    ) -> Path:
        out_path = run_dir / (filename or self.records_filename)
        if self.format == "parquet":
            pd.DataFrame(rows).to_parquet(out_path, index=False)
        else:
            fieldnames = list(self.model.model_fields.keys())
            _write_csv(rows, out_path, fieldnames)
        return out_path

    def append_records(
        self,
        rows: list[dict[str, Any]],
        run_dir: Path,
        *,
        filename: str | None = None,
    ) -> Path:
        validated = [self.model.model_validate(row).model_dump() for row in rows]
        out_path = run_dir / (filename or self.records_filename)
        if self.format == "parquet":
            if out_path.exists():
                existing = pd.read_parquet(out_path)
                new_df = pd.DataFrame(validated)
                if set(existing.columns) != set(new_df.columns):
                    raise ValueError(
                        f"""
                        Schema mismatch: existing={set(existing.columns)}, new={set(new_df.columns)}
                        """
                    )
                combined = pd.concat([existing, new_df], ignore_index=True)
            else:
                combined = pd.DataFrame(validated)
            combined.to_parquet(out_path, index=False)
        else:
            fieldnames = list(self.model.model_fields.keys())
            _append_csv(validated, out_path, fieldnames)
        return out_path

    def load_seen_ids(
        self,
        run_dir: Path,
        id_column: str,
        *,
        filename: str | None = None,
    ) -> set[str]:
        out_path = run_dir / (filename or self.records_filename)
        if not out_path.exists():
            return set()
        if self.format == "parquet":
            df = pd.read_parquet(out_path, columns=[id_column])
            return {str(v) for v in df[id_column] if v}
        with out_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return {row[id_column] for row in reader if row.get(id_column)}

    def load_seen_ids_from_athena(self) -> set[str]:
        # TODO: SELECT id FROM dedupe_seen_ids WHERE platform = self.platform
        return set()

    def append_deduped_records(
        self,
        rows: list[dict[str, Any]],
        run_dir: Path,
        *,
        dedupe_session: DedupeSession,
        filename: str | None = None,
    ) -> AppendResult:
        kept_rows, skipped = dedupe_session.filter_rows(rows)
        resolved_filename = filename or dedupe_session.config.filename
        if kept_rows:
            self.append_records(kept_rows, run_dir, filename=resolved_filename)
            dedupe_session.note_appended(kept_rows)
        return AppendResult(kept=len(kept_rows), skipped=skipped)

    def load_seen_uris(
        self,
        run_dir: Path,
        *,
        filename: str | None = None,
    ) -> set[str]:
        return self.load_seen_ids(run_dir, "uri", filename=filename)

    def load_records(
        self,
        run_dir: Path | None = None,
        *,
        latest: bool = False,
        filename: str | None = None,
    ) -> pd.DataFrame:
        resolved_run_dir = self._resolve_run_dir(run_dir, latest=latest)
        out_path = resolved_run_dir / (filename or self.records_filename)
        if not out_path.exists():
            raise FileNotFoundError(f"Records file not found: {out_path}")
        if self.format == "parquet":
            return pd.read_parquet(out_path)
        return pd.read_csv(out_path, keep_default_na=False)

    def write_dataframe(
        self,
        df: pd.DataFrame,
        run_dir: Path,
        *,
        filename: str | None = None,
    ) -> Path:
        out_path = run_dir / (filename or self.records_filename)
        if self.format == "parquet":
            df.to_parquet(out_path, index=False)
        else:
            df.to_csv(out_path, index=False)
        return out_path

    def write_run_metadata(self, run_dir: Path, metadata: dict[str, Any]) -> Path:
        metadata_path = run_dir / METADATA_FILENAME
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        return metadata_path

    def write_run_metadata_atomic(self, run_dir: Path, metadata: dict[str, Any]) -> Path:
        metadata_path = run_dir / METADATA_FILENAME
        tmp_path = run_dir / f"{METADATA_FILENAME}.tmp"
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        tmp_path.replace(metadata_path)
        return metadata_path

    def filename_for(self, stem: str) -> str:
        """Return the format-correct filename for a given stem."""
        return f"{stem}.{self.format.value}"

    def load_run_metadata(
        self,
        run_dir: Path | None = None,
        *,
        latest: bool = False,
    ) -> dict[str, Any]:
        resolved_run_dir = self._resolve_run_dir(run_dir, latest=latest)
        metadata_path = resolved_run_dir / METADATA_FILENAME
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {metadata_path}")
        with metadata_path.open(encoding="utf-8") as f:
            return json.load(f)


class BlueskyStorageManager(StorageManager):
    def __init__(
        self,
        stage: StorageStage = StorageStage.RAW,
        dataset_id: str = "",
        *,
        records_filename: str = "posts.csv",
    ) -> None:
        super().__init__(
            "bluesky",
            stage,
            SyncBlueskyPostModel,
            dataset_id,
            records_filename=records_filename,
        )


class RedditStorageManager(StorageManager):
    def __init__(
        self,
        stage: StorageStage = StorageStage.RAW,
        dataset_id: str = "",
        *,
        records_filename: str = "comments.csv",
        model: type[BaseModel] | None = None,
    ) -> None:
        super().__init__(
            "reddit",
            stage,
            model or SyncRedditCommentModel,
            dataset_id,
            records_filename=records_filename,
        )

    def comment_storage(self) -> RedditStorageManager:
        return RedditStorageManager(
            self.stage,
            self.dataset_id,
            records_filename="comments.csv",
            model=SyncRedditCommentModel,
        )

    def post_storage(self) -> RedditStorageManager:
        return RedditStorageManager(
            self.stage,
            self.dataset_id,
            records_filename="posts.csv",
            model=SyncRedditPostModel,
        )


class TwitterStorageManager(StorageManager):
    def __init__(
        self,
        stage: StorageStage = StorageStage.RAW,
        dataset_id: str = "",
        *,
        records_filename: str = "posts.csv",
    ) -> None:
        super().__init__(
            "twitter",
            stage,
            SyncTwitterPostModel,
            dataset_id,
            records_filename=records_filename,
        )

    def load_records(
        self,
        run_dir: Path | None = None,
        *,
        latest: bool = False,
        filename: str | None = None,
    ) -> pd.DataFrame:
        resolved_run_dir = self._resolve_run_dir(run_dir, latest=latest)
        csv_path = resolved_run_dir / (filename or self.records_filename)
        if not csv_path.exists():
            raise FileNotFoundError(f"Records file not found: {csv_path}")

        return pd.read_csv(
            csv_path,
            keep_default_na=False,
            dtype={"tweet_id": "string", "author_id": "string"},
        )

    def load_seen_tweet_ids(
        self,
        run_dir: Path,
        *,
        filename: str | None = None,
    ) -> set[str]:
        return self.load_seen_ids(run_dir, "tweet_id", filename=filename)
