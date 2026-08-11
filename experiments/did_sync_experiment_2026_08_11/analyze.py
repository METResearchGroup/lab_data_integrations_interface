"""Enrich discovered DIDs via getRepo and classify validity.

Run from repo root::

    PYTHONPATH=. uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ProfileStats:
    """Per-DID profile and six month activity metrics."""

    did: str
    handle: str | None = None
    followers: int | None = None
    followees: int | None = None
    posts: int | None = None
    account_created_at: str | None = None
    original_posts_6m: int | None = None
    interactions_6m: int | None = None
    likes_6m: int | None = None
    reposts_6m: int | None = None
    replies_6m: int | None = None
    quotes_6m: int | None = None
    bookmarks_6m: int | None = None
    valid: bool | None = None
    invalid_reasons: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize profile metrics for JSONL output."""
        return asdict(self)


@dataclass
class AnalyzeMeta:
    """Aggregate getRepo and AppView metrics for one ablation."""

    getrepo_request_count: int
    getrepo_error_count: int
    getrepo_rate_limit_event_count: int
    getrepo_runtime_seconds: float
    appview_profile_request_count: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize analysis metrics for summary JSON."""
        return asdict(self)


def analyze_dids(dids: list[str], workers: int) -> tuple[list[ProfileStats], AnalyzeMeta]:
    """Fetch repos for DIDs and classify validity.

    Parameters
    ----------
    dids
        Unique account IDs to enrich.
    workers
        Parallel getRepo worker count.

    Returns
    -------
    tuple[list[ProfileStats], AnalyzeMeta]
        Per-DID rows and aggregate analysis metrics.
    """
    raise NotImplementedError("analyze_dids is implemented in step 4")
