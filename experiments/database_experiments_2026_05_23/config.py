"""Benchmark configuration and scale caps.

Run from repo root:
    PYTHONPATH=. uv run python -c "from experiments.database_experiments_2026_05_23.config import BenchmarkConfig"
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ScaleCaps:
    users: int
    posts: int
    likes: int
    follows: int


SMOKE_CAPS = ScaleCaps(users=50, posts=5_000, likes=10_000, follows=500)
FULL_CAPS = ScaleCaps(users=5_000, posts=1_000_000, likes=1_500_000, follows=30_000)

DEFAULT_MOCK_DATA_DIR = Path("experiments/database_experiments_2026_05_23/mock_data")
DEFAULT_SQLITE_DATA_DIR = Path("experiments/database_experiments_2026_05_23/sqlite_data")
DEFAULT_OUTPUT_DIR = Path("experiments/database_experiments_2026_05_23/data")
EXPERIMENT_ROOT = Path("experiments/database_experiments_2026_05_23")


def ensure_repo_import_path() -> None:
    """Drop script-dir sys.path entry so local `duckdb/` does not shadow the library."""
    import sys

    experiment_root = Path(__file__).resolve().parent
    if sys.path and Path(sys.path[0]).resolve() == experiment_root:
        sys.path.pop(0)

BACKEND_ORDER = ("postgres", "sqlite", "duckdb")
SAMPLE_AUTHOR_COUNT = 100


@dataclass
class BenchmarkConfig:
    threads: int = 8
    iterations: int = 3
    warmup: int = 2
    scale: str = "full"
    mock_data_dir: Path = field(default_factory=lambda: DEFAULT_MOCK_DATA_DIR)
    output_dir: Path = field(default_factory=lambda: DEFAULT_OUTPUT_DIR)
    sqlite_data_dir: Path = field(default_factory=lambda: DEFAULT_SQLITE_DATA_DIR)
    backends: tuple[str, ...] = BACKEND_ORDER
    postgres_dsn: str | None = None
    skip_postgres: bool = False

    @property
    def caps(self) -> ScaleCaps:
        return SMOKE_CAPS if self.scale == "smoke" else FULL_CAPS
