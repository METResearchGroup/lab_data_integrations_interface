"""DID discovery for PLC export and AOC follower breadth first search.

Run from repo root::

    PYTHONPATH=. uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from atproto import Client


@dataclass
class RateLimitEvent:
    """One observed rate limit response during discovery."""

    source: str
    at_unix: float
    status_code: int | None
    detail: str
    retry_after: str | None = None


@dataclass
class DiscoveryResult:
    """Unique DIDs plus request, runtime, and rate limit metrics."""

    ablation: str
    dids: list[str]
    request_count: int
    runtime_seconds: float
    rate_limit_events: list[RateLimitEvent] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize discovery metrics for JSON output."""
        return {
            "ablation": self.ablation,
            "did_count": len(self.dids),
            "dids": self.dids,
            "request_count": self.request_count,
            "runtime_seconds": self.runtime_seconds,
            "rate_limit_events": [asdict(event) for event in self.rate_limit_events],
            "extra": self.extra,
        }


def discover_plc_dids(target: int) -> DiscoveryResult:
    """Collect unique DIDs from PLC export starting at a recent cursor.

    Parameters
    ----------
    target
        Number of unique DIDs to collect.

    Returns
    -------
    DiscoveryResult
        Ordered unique DIDs and discovery metrics.
    """
    raise NotImplementedError("discover_plc_dids is implemented in step 2")


def discover_aoc_bfs_dids(target: int, client: Client | None = None) -> DiscoveryResult:
    """Collect unique DIDs by breadth first search over AOC followers.

    Parameters
    ----------
    target
        Number of unique DIDs to collect.
    client
        Optional AppView client. When omitted, a public client is created.

    Returns
    -------
    DiscoveryResult
        Ordered unique DIDs and discovery metrics.
    """
    raise NotImplementedError("discover_aoc_bfs_dids is implemented in step 3")
