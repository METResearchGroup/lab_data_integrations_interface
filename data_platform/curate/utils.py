"""Curate-specific config path helpers."""

from __future__ import annotations

from pathlib import Path

from data_platform.utils.config_paths import resolve_config_path


def resolve_curate_config_path(config: Path, configs_dir: Path) -> Path:
    return resolve_config_path(config, configs_dir)
