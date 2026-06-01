"""Shared YAML config path resolution for pipeline entrypoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def resolve_config_path(config: Path, configs_dir: Path) -> Path:
    """Resolve a config path from CLI input, optional .yaml suffix, or configs_dir."""
    candidates = [config]
    if config.suffix != ".yaml":
        candidates.append(config.with_suffix(".yaml"))
    if config.parent == Path("."):
        candidates.extend(configs_dir / candidate.name for candidate in list(candidates))

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    raise FileNotFoundError(f"Config not found: {config}")


def load_yaml_config(config_path: Path) -> dict[str, Any]:
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)
