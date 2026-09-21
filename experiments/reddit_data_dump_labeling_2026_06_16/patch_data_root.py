from __future__ import annotations

from pathlib import Path

from experiments.reddit_data_dump_labeling_2026_06_16.paths import EXPERIMENT_DATA_ROOT


def patch_data_root(data_root: Path | None = None) -> Path:
    """Point prod storage/dataset helpers at the experiment data tree."""
    root = data_root or EXPERIMENT_DATA_ROOT
    import data_platform.utils.dataset as dataset
    import data_platform.utils.storage as storage

    storage.DATA_ROOT = root
    dataset._DATA_ROOT = root
    return root
