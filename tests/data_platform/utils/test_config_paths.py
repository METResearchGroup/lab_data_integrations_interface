from __future__ import annotations

from pathlib import Path

import pytest

from data_platform.utils.config_paths import load_yaml_config, resolve_config_path


def test_resolve_config_path_bare_filename(tmp_path: Path) -> None:
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    config_file = configs_dir / "mirrorview.yaml"
    config_file.write_text("name: test\n", encoding="utf-8")

    resolved = resolve_config_path(Path("mirrorview"), configs_dir)

    assert resolved == config_file.resolve()


def test_resolve_config_path_adds_yaml_suffix(tmp_path: Path) -> None:
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    config_file = configs_dir / "default.yaml"
    config_file.write_text("name: default\n", encoding="utf-8")

    resolved = resolve_config_path(Path("default"), configs_dir)

    assert resolved == config_file.resolve()


def test_resolve_config_path_absolute_path(tmp_path: Path) -> None:
    config_file = tmp_path / "custom.yaml"
    config_file.write_text("dataset_id: bluesky_test\n", encoding="utf-8")
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()

    resolved = resolve_config_path(config_file, configs_dir)

    assert resolved == config_file.resolve()


def test_resolve_config_path_missing_raises(tmp_path: Path) -> None:
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()

    with pytest.raises(FileNotFoundError, match="Config not found"):
        resolve_config_path(Path("missing.yaml"), configs_dir)


def test_load_yaml_config(tmp_path: Path) -> None:
    config_file = tmp_path / "test.yaml"
    config_file.write_text("dataset_id: bluesky_abc\n", encoding="utf-8")

    loaded = load_yaml_config(config_file)

    assert loaded == {"dataset_id": "bluesky_abc"}
