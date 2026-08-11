"""AOC cohort getRepo derived-stats experiment entrypoint.

Run from repo root::

    PYTHONPATH=. uv run python experiments/aoc_getrepo_derived_stats_2026_08_11/main.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from experimentation.aoc_followers_backfill.client import (
    create_public_client,
    create_relay_client,
)
from experiments.aoc_getrepo_derived_stats_2026_08_11.constants import DAYS_BACK
from experiments.aoc_getrepo_derived_stats_2026_08_11.derive import derive_stats
from experiments.aoc_getrepo_derived_stats_2026_08_11.discovery import discover_cohort
from experiments.aoc_getrepo_derived_stats_2026_08_11.fetch_repos import fetch_cohort_repos
from experiments.aoc_getrepo_derived_stats_2026_08_11.output import write_outputs


def run() -> None:
    """Discover the cohort, fetch repos, derive stats, and write outputs."""
    run_start = datetime.now(UTC)
    window_end = run_start
    window_start = run_start - timedelta(days=DAYS_BACK)

    public_client = create_public_client()
    cohort = discover_cohort(public_client)
    print(f"Discovered cohort size: {len(cohort.members)}")

    relay_client = create_relay_client()
    bundles = fetch_cohort_repos(cohort.members, relay_client)
    success_count = sum(1 for bundle in bundles if bundle.error is None)
    failed_count = len(bundles) - success_count
    print(f"Repos: {success_count} ok, {failed_count} failed")

    derived = derive_stats(cohort.members, bundles, window_start, window_end)
    output_dir = write_outputs(
        members=cohort.members,
        bundles=bundles,
        derived_stats=derived,
        run_start=run_start,
        window_start=window_start,
        window_end=window_end,
    )
    print(f"Wrote output to {output_dir}")


if __name__ == "__main__":
    run()
