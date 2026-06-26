from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import data_platform.utils.dataset as dataset_mod
import data_platform.utils.storage as storage_mod
from tests.data_platform.constants import (
    LABEL_TIMESTAMP,
    SAMPLE_INGESTION_ROW,
    URI_POST_A,
    URI_POST_B,
)


@pytest.fixture(autouse=True)
def mock_athena(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent any test from making real Athena calls. Tests that need specific
    IDs returned can override with their own monkeypatch.setattr."""
    monkeypatch.setattr(storage_mod.StorageManager, "load_seen_ids_from_athena", lambda self: set())
    monkeypatch.setattr(
        storage_mod.StorageManager,
        "load_seen_ids_from_athena_for_feature",
        lambda self, feature_name: set(),
    )


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point storage and dataset modules at an isolated data directory."""
    root = tmp_path / "data"
    monkeypatch.setattr(storage_mod, "DATA_ROOT", root)
    monkeypatch.setattr(dataset_mod, "_DATA_ROOT", root)
    return root


def make_post_row(
    *,
    uri: str = URI_POST_A,
    text: str = "post one",
    url: str | None = None,
    author_handle: str = "a.bsky.social",
    created_at: str = "2026-01-01T00:00:00Z",
    like_count: int = 0,
) -> dict[str, Any]:
    handle = author_handle.removesuffix(".bsky.social")
    return {
        "uri": uri,
        "url": url or f"https://bsky.app/profile/{handle}/post/1",
        "author_handle": author_handle,
        "text": text,
        "created_at": created_at,
        "like_count": like_count,
        "repost_count": 0,
        "reply_count": 0,
        "quote_count": 0,
    }


def write_posts_file(path: Path, rows: list[Mapping[str, Any]] | None = None) -> Path:
    if rows is None:
        rows = [
            make_post_row(uri=URI_POST_A, text="post one"),
            make_post_row(
                uri=URI_POST_B,
                text="post two",
                author_handle="b.bsky.social",
                created_at="2026-01-02T00:00:00Z",
                like_count=1,
            ),
        ]
    pd.DataFrame(list(rows)).to_csv(path, index=False)
    return path


def write_feature_csv(
    features_root: Path,
    feature_name: str,
    rows: list[Mapping[str, Any]],
) -> Path:
    features_root.mkdir(parents=True, exist_ok=True)
    path = features_root / f"{feature_name}.csv"
    pd.DataFrame(list(rows)).to_csv(path, index=False)
    return path


def make_political_feature_rows() -> list[dict[str, Any]]:
    return [
        {
            "uri": URI_POST_A,
            "label_timestamp": LABEL_TIMESTAMP,
            "is_political": True,
        },
        {
            "uri": URI_POST_B,
            "label_timestamp": LABEL_TIMESTAMP,
            "is_political": False,
        },
    ]


def make_ingestion_row(**overrides: Any) -> dict[str, Any]:
    return {**SAMPLE_INGESTION_ROW, **overrides}
