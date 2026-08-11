"""Run DID-sync discovery ablations and compare valid-account yield.

Ablation 1: PLC directory export → 1000 unique DIDs
Ablation 2: BFS over AOC followers → 1000 unique DIDs

For each DID, fetch the repo via com.atproto.sync.getRepo (same approach as
experimentation/aoc_followers_backfill), derive posts/followees/6-month activity,
overlay AppView follower counts, and apply validity thresholds.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from experimentation.aoc_followers_backfill.client import create_public_client
from experiments.did_sync_experiment_2026_08_11.analyze import analyze_dids
from experiments.did_sync_experiment_2026_08_11.discover import (
    discover_aoc_bfs_dids,
    discover_plc_dids,
)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def run_ablation(
    name: str,
    discovery,
    *,
    workers: int,
    limit: int | None = None,
) -> dict:
    print(f"\n=== {name}: discovery ===", flush=True)
    result = discovery()
    if limit is not None:
        result.dids = result.dids[:limit]
    out_dir = DATA / name
    out_dir.mkdir(parents=True, exist_ok=True)

    discovery_payload = result.to_dict()
    _write_json(out_dir / "discovery.json", discovery_payload)
    print(
        f"Discovered {len(result.dids)} DIDs in {result.runtime_seconds:.2f}s "
        f"via {result.request_count} requests; "
        f"rate_limits={len(result.rate_limit_events)}",
        flush=True,
    )

    print(f"=== {name}: getRepo analysis ===", flush=True)
    profiles, meta = analyze_dids(result.dids, workers=workers)
    _write_jsonl(out_dir / "profiles.jsonl", [p.to_dict() for p in profiles])

    summary = {
        "ablation": name,
        "did_count": len(profiles),
        "valid_did_count": sum(1 for p in profiles if p.valid),
        "invalid_did_count": sum(1 for p in profiles if p.valid is False),
        "discovery": {
            "request_count": result.request_count,
            "runtime_seconds": result.runtime_seconds,
            "rate_limit_event_count": len(result.rate_limit_events),
            "extra": result.extra,
        },
        "analysis": meta,
        "validity_rate": (
            sum(1 for p in profiles if p.valid) / len(profiles) if profiles else 0.0
        ),
    }
    _write_json(out_dir / "summary.json", summary)
    print(
        f"Valid {summary['valid_did_count']}/{summary['did_count']} "
        f"({100 * summary['validity_rate']:.1f}%)",
        flush=True,
    )
    return summary


def write_results_md(summaries: list[dict], run_started: datetime) -> None:
    lines: list[str] = []
    lines.append("# DID sync discovery experiment — 2026-08-11")
    lines.append("")
    lines.append(f"Run started (UTC): `{run_started.isoformat()}`")
    lines.append("")
    lines.append("## Question")
    lines.append("")
    lines.append(
        "Which DID discovery strategy yields more *valid* accounts (by activity/"
        "graph thresholds) when sampling 1000 DIDs?"
    )
    lines.append("")
    lines.append("## Validity criteria")
    lines.append("")
    lines.append("An account is **valid** if all of the following hold:")
    lines.append("")
    lines.append("1. At least **10** followers (AppView `followersCount`)")
    lines.append("2. At least **10** followees (`app.bsky.graph.follow` records via `getRepo`)")
    lines.append(
        "3. At least **20** original posts in the last ~6 months "
        "(`app.bsky.feed.post` without `reply`)"
    )
    lines.append(
        "4. At least **20** interactions in the last ~6 months "
        "(like + save/bookmark + quote + repost + reply)"
    )
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append(
        "- **Ablation 1 (PLC):** `https://plc.directory/export` from genesis, unique DIDs."
    )
    lines.append(
        "- **Ablation 2 (AOC BFS):** `getFollowers` BFS starting at `aoc.bsky.social`."
    )
    lines.append(
        "- **Profile/activity:** `com.atproto.sync.getRepo` against `bsky.network` "
        "(same decode approach as `experimentation/aoc_followers_backfill`), plus "
        "AppView `getProfiles` for follower counts / handles / createdAt "
        "(follower edges are not present in a user's own repo)."
    )
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append(
        "| Ablation | DIDs | Valid DIDs | Validity rate | Discovery requests | "
        "Discovery runtime (s) | Discovery rate-limits | getRepo requests | "
        "getRepo rate-limits | getRepo errors |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in summaries:
        lines.append(
            "| {ablation} | {dids} | {valid} | {rate:.1%} | {dreq} | {drun:.2f} | "
            "{drl} | {greq} | {grl} | {gerr} |".format(
                ablation=s["ablation"],
                dids=s["did_count"],
                valid=s["valid_did_count"],
                rate=s["validity_rate"],
                dreq=s["discovery"]["request_count"],
                drun=s["discovery"]["runtime_seconds"],
                drl=s["discovery"]["rate_limit_event_count"],
                greq=s["analysis"]["getrepo_request_count"],
                grl=s["analysis"]["rate_limited_count"],
                gerr=s["analysis"]["error_count"],
            )
        )
    lines.append("")

    if len(summaries) == 2:
        a, b = summaries[0], summaries[1]
        better = (
            a
            if a["valid_did_count"] > b["valid_did_count"]
            else b
            if b["valid_did_count"] > a["valid_did_count"]
            else None
        )
        lines.append("## Comparison")
        lines.append("")
        if better is None:
            lines.append(
                f"Both ablations yielded the same number of valid DIDs "
                f"({a['valid_did_count']})."
            )
        else:
            other = b if better is a else a
            lines.append(
                f"**{better['ablation']}** produced more valid DIDs "
                f"({better['valid_did_count']} vs {other['valid_did_count']}, "
                f"{better['validity_rate']:.1%} vs {other['validity_rate']:.1%})."
            )
        lines.append("")
        lines.append("### Discovery cost")
        lines.append("")
        for s in summaries:
            extra = s["discovery"].get("extra") or {}
            lines.append(
                f"- **{s['ablation']}**: {s['discovery']['request_count']} requests, "
                f"{s['discovery']['runtime_seconds']:.2f}s, "
                f"{s['discovery']['rate_limit_event_count']} rate-limit events."
            )
            if s["ablation"].startswith("ablation1"):
                lines.append(
                    f"  - PLC pages / final cursor: `{extra.get('pages')}` / "
                    f"`{extra.get('final_after_cursor')}`"
                )
                if extra.get("last_rate_limit_headers"):
                    lines.append(
                        f"  - Observed rate-limit related headers: "
                        f"`{extra.get('last_rate_limit_headers')}`"
                    )
                else:
                    lines.append("  - No rate-limit related response headers observed.")
            if s["ablation"].startswith("ablation2"):
                lines.append(
                    f"  - Seed: `{extra.get('seed_handle')}` "
                    f"({extra.get('seed_did')}), "
                    f"followers≈{extra.get('seed_followers_count')}"
                )
                lines.append(
                    f"  - Max BFS depth reached: `{extra.get('max_depth_reached')}`, "
                    f"pages by depth: `{extra.get('pages_by_depth')}`"
                )
        lines.append("")
        lines.append("### Interpretation")
        lines.append("")
        lines.append(
            "- PLC genesis export preferentially samples the earliest registered DIDs "
            "(often highly active Bluesky staff/early adopters, but also includes "
            "dormant invite-era accounts and some very large repos)."
        )
        lines.append(
            "- AOC follower BFS preferentially samples accounts that follow a "
            "high-engagement political account (and, at deeper levels, followers of "
            "those followers), which may skew toward currently active users."
        )
        lines.append(
            "- Validity requires recent original posting *and* interactions, so "
            "discovery methods that surface currently engaged graph neighborhoods "
            "should outperform raw PLC chronology if early DIDs are mostly inactive."
        )

    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    lines.append("Per ablation under `data/<ablation>/`:")
    lines.append("")
    lines.append("- `discovery.json` — DIDs, request/runtime/rate-limit metrics")
    lines.append("- `profiles.jsonl` — per-DID follower/post/followee/created + activity")
    lines.append("- `summary.json` — rollup counts used in this file")
    lines.append("")

    (ROOT / "RESULTS.md").write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=1000, help="DIDs per ablation")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent getRepo workers")
    parser.add_argument(
        "--only",
        choices=["ablation1_plc", "ablation2_aoc_bfs", "both"],
        default="both",
    )
    args = parser.parse_args(argv)

    run_started = datetime.now(UTC)
    DATA.mkdir(parents=True, exist_ok=True)
    _write_json(
        DATA / "run_meta.json",
        {"started_at": run_started.isoformat(), "target": args.target, "workers": args.workers},
    )

    summaries: list[dict] = []

    if args.only in {"ablation1_plc", "both"}:
        summaries.append(
            run_ablation(
                "ablation1_plc",
                lambda: discover_plc_dids(args.target),
                workers=args.workers,
            )
        )

    if args.only in {"ablation2_aoc_bfs", "both"}:
        client = create_public_client()
        summaries.append(
            run_ablation(
                "ablation2_aoc_bfs",
                lambda: discover_aoc_bfs_dids(client, args.target),
                workers=args.workers,
            )
        )

    write_results_md(summaries, run_started)
    _write_json(DATA / "summaries.json", summaries)
    print(f"\nWrote {ROOT / 'RESULTS.md'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
