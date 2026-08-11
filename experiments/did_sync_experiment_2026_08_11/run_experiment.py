"""Run DID sync discovery ablations and write comparison artifacts.

Run from repo root::

    PYTHONPATH=. uv run python -m experiments.did_sync_experiment_2026_08_11.run_experiment --smoke
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from experiments.did_sync_experiment_2026_08_11.analyze import AnalyzeMeta, ProfileStats, analyze_dids
from experiments.did_sync_experiment_2026_08_11.constants import (
    ABLATION1_NAME,
    ABLATION2_NAME,
    DEFAULT_WORKERS,
    SMOKE_TARGET_DIDS,
    SUMMARY_KEYS,
    TARGET_DIDS,
)
from experiments.did_sync_experiment_2026_08_11.discover import (
    DiscoveryResult,
    discover_aoc_bfs_dids,
    discover_plc_dids,
)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


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


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def build_summary(
    ablation: str,
    discovery: DiscoveryResult,
    profiles: list[ProfileStats],
    analysis: AnalyzeMeta,
) -> dict:
    """Build the frozen summary.json payload for one ablation."""
    valid_count = sum(1 for profile in profiles if profile.valid)
    did_count = len(profiles)
    summary = {
        "ablation": ablation,
        "did_count": did_count,
        "valid_did_count": valid_count,
        "invalid_did_count": sum(1 for profile in profiles if profile.valid is False),
        "validity_rate": (valid_count / did_count) if did_count else 0.0,
        "discovery": {
            "request_count": discovery.request_count,
            "runtime_seconds": discovery.runtime_seconds,
            "rate_limit_event_count": len(discovery.rate_limit_events),
            "extra": discovery.extra,
        },
        "analysis": analysis.to_dict(),
    }
    assert set(SUMMARY_KEYS) <= set(summary.keys())
    return summary


def write_results_md(summaries: list[dict], run_started: datetime) -> str:
    """Render RESULTS.md comparison text from ablation summaries."""
    lines: list[str] = []
    lines.append("# DID sync discovery experiment, 2026-08-11")
    lines.append("")
    lines.append(f"Run started (UTC): `{run_started.isoformat()}`")
    lines.append("")
    lines.append("## Question")
    lines.append("")
    lines.append(
        "Which DID discovery strategy yields more valid accounts under shared "
        "activity and graph thresholds when sampling the same number of DIDs?"
    )
    lines.append("")
    lines.append("## Validity criteria")
    lines.append("")
    lines.append("An account is valid when all of the following hold:")
    lines.append("")
    lines.append("1. At least 10 followers (AppView `followersCount`)")
    lines.append("2. At least 10 followees (`app.bsky.graph.follow` via `getRepo`)")
    lines.append("3. At least 20 original posts in the last ~6 months")
    lines.append(
        "4. At least 20 interactions in the last ~6 months "
        "(like + bookmark/save + quote + repost + reply)"
    )
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append(
        "- Ablation 1 (PLC): `https://plc.directory/export` from a recent cursor, unique DIDs."
    )
    lines.append(
        "- Ablation 2 (AOC BFS): `getFollowers` breadth first search starting at `aoc.bsky.social`."
    )
    lines.append(
        "- Profile and activity: `com.atproto.sync.getRepo` against `bsky.network` "
        "(decode helpers from `experimentation/aoc_followers_backfill`), plus AppView "
        "`getProfiles` for follower counts and handles."
    )
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append(
        "| Ablation | DIDs | Valid DIDs | Validity rate | Discovery requests | "
        "Discovery runtime (s) | Discovery rate-limits | getRepo requests | "
        "getRepo rate-limits | getRepo errors |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    for summary in summaries:
        discovery = summary["discovery"]
        analysis = summary["analysis"]
        lines.append(
            f"| {summary['ablation']} | {summary['did_count']} | "
            f"{summary['valid_did_count']} | {100 * summary['validity_rate']:.1f}% | "
            f"{discovery['request_count']} | {discovery['runtime_seconds']:.2f} | "
            f"{discovery['rate_limit_event_count']} | "
            f"{analysis['getrepo_request_count']} | "
            f"{analysis['getrepo_rate_limit_event_count']} | "
            f"{analysis['getrepo_error_count']} |"
        )
    lines.append("")
    lines.append("## Comparison")
    lines.append("")
    if len(summaries) >= 2:
        left, right = summaries[0], summaries[1]
        if left["valid_did_count"] >= right["valid_did_count"]:
            winner, loser = left, right
        else:
            winner, loser = right, left
        delta = winner["valid_did_count"] - loser["valid_did_count"]
        lines.append(
            f"{winner['ablation']} produced more valid DIDs "
            f"({winner['valid_did_count']} vs {loser['valid_did_count']}, "
            f"delta {delta}; "
            f"{100 * winner['validity_rate']:.1f}% vs {100 * loser['validity_rate']:.1f}%)."
        )
    elif summaries:
        only = summaries[0]
        lines.append(
            f"Only `{only['ablation']}` ran, with "
            f"{only['valid_did_count']}/{only['did_count']} valid DIDs."
        )
    lines.append("")
    lines.append("### Discovery cost")
    lines.append("")
    for summary in summaries:
        discovery = summary["discovery"]
        lines.append(
            f"- {summary['ablation']}: {discovery['request_count']} requests, "
            f"{discovery['runtime_seconds']:.2f}s, "
            f"{discovery['rate_limit_event_count']} rate-limit events."
        )
        extra = discovery.get("extra") or {}
        for key, value in extra.items():
            lines.append(f"  - `{key}`: `{value}`")
    lines.append("")
    lines.append("### Interpretation")
    lines.append("")
    lines.append(
        "PLC recent-cursor export samples accounts that registered or updated "
        "identity operations near the lookback window, which may mix active new "
        "accounts with dormant ones."
    )
    lines.append("")
    lines.append(
        "AOC follower breadth first search samples accounts connected to a high "
        "engagement political neighborhood, which may skew toward currently active users."
    )
    lines.append("")
    lines.append(
        "Validity requires recent original posting and interactions, so the method "
        "that surfaces currently engaged graph neighborhoods should outperform recent "
        "PLC chronology when newly registered DIDs are inactive or when getRepo fails "
        "often for that sample. These numbers inform backfill seed choice. They do not "
        "by themselves prove production readiness."
    )
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    lines.append("Per ablation under `data/<ablation>/`:")
    lines.append("")
    lines.append("- `discovery.json`: DIDs, request/runtime/rate-limit metrics")
    lines.append("- `profiles.jsonl`: per-DID follower/post/followee/created + activity")
    lines.append("- `summary.json`: rollup counts used in this file")
    lines.append("")
    return "\n".join(lines)


def run_ablation(
    name: str,
    discovery_fn: Callable[[], DiscoveryResult],
    workers: int,
) -> dict:
    """Run discovery plus analysis for one ablation and write artifacts."""
    print(f"\n=== {name}: discovery ===", flush=True)
    discovery = discovery_fn()
    out_dir = DATA / name
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "discovery.json", discovery.to_dict())
    print(
        f"Discovered {len(discovery.dids)} DIDs in {discovery.runtime_seconds:.2f}s "
        f"via {discovery.request_count} requests; "
        f"rate_limits={len(discovery.rate_limit_events)}",
        flush=True,
    )

    print(f"=== {name}: getRepo analysis ===", flush=True)
    profiles, meta = analyze_dids(discovery.dids, workers=workers)
    _write_jsonl(out_dir / "profiles.jsonl", [profile.to_dict() for profile in profiles])
    summary = build_summary(name, discovery, profiles, meta)
    _write_json(out_dir / "summary.json", summary)
    print(
        f"Valid {summary['valid_did_count']}/{summary['did_count']} "
        f"({100 * summary['validity_rate']:.1f}%)",
        flush=True,
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    """Run selected ablations and write RESULTS.md."""
    parser = build_parser()
    args = parser.parse_args(argv)
    target = resolve_target(args.target, args.smoke)
    run_started = datetime.now(UTC)
    DATA.mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[str, Callable[[], DiscoveryResult]]] = []
    if args.only in ("both", "plc"):
        jobs.append((ABLATION1_NAME, lambda: discover_plc_dids(target)))
    if args.only in ("both", "aoc"):
        jobs.append((ABLATION2_NAME, lambda: discover_aoc_bfs_dids(target)))

    summaries = [
        run_ablation(name, discovery_fn, workers=args.workers) for name, discovery_fn in jobs
    ]

    _write_json(DATA / "summaries.json", summaries)
    _write_json(
        DATA / "run_meta.json",
        {
            "run_started_utc": run_started.isoformat(),
            "target": target,
            "workers": args.workers,
            "only": args.only,
            "smoke": args.smoke,
        },
    )
    results_text = write_results_md(summaries, run_started)
    (ROOT / "RESULTS.md").write_text(results_text)
    print(f"\nWrote {ROOT / 'RESULTS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
