"""Run DID sync discovery ablations and write comparison artifacts.

Run from repo root::

    PYTHONPATH=. uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment --smoke
"""

from __future__ import annotations

import argparse
import sys

from experiments.did_sync_experiment_2026_08_11.constants import (
    DEFAULT_WORKERS,
    SMOKE_TARGET_DIDS,
    TARGET_DIDS,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the experiment CLI parser."""
    parser = argparse.ArgumentParser(
        description="Compare PLC export vs AOC follower BFS DID discovery quality."
    )
    parser.add_argument(
        "--target",
        type=int,
        default=None,
        help=f"Unique DIDs per ablation (default {TARGET_DIDS}, or {SMOKE_TARGET_DIDS} with --smoke)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Parallel getRepo workers (default {DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--only",
        choices=("both", "plc", "aoc"),
        default="both",
        help="Which ablation(s) to run (default both)",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=f"Use target={SMOKE_TARGET_DIDS} when --target is omitted",
    )
    return parser


def resolve_target(target: int | None, smoke: bool) -> int:
    """Choose the DID target from CLI flags."""
    if target is not None:
        return target
    if smoke:
        return SMOKE_TARGET_DIDS
    return TARGET_DIDS


def main(argv: list[str] | None = None) -> int:
    """Parse CLI args. Discovery and analysis land in later steps."""
    parser = build_parser()
    args = parser.parse_args(argv)
    target = resolve_target(args.target, args.smoke)
    print(
        f"DID sync experiment configured: target={target} workers={args.workers} "
        f"only={args.only}. Discovery/analyze not wired yet.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
