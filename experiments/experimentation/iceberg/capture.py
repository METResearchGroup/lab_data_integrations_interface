"""Phase 1 -- capture the Bluesky Jetstream firehose to a local file.

Deliberately decoupled from the S3/Iceberg write path. A 10-minute capture is
expensive to re-collect and never reproducible, so it is recorded once and then
replayed as many times as needed. That keeps every write-path variant (flush
interval, partition spec, compaction strategy) measured against byte-identical
input.

Usage:
    python -m experimentation.iceberg.capture --seconds 600
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import websockets

from experimentation.iceberg import constants

CAPTURE_DIR = Path(__file__).parent / "data" / "captures"


def build_endpoint() -> str:
    """Jetstream subscribe URL filtered to the four collections we care about."""
    query = urlencode([("wantedCollections", nsid) for nsid in constants.COLLECTIONS])
    return f"{constants.JETSTREAM_ENDPOINT}?{query}"


def _tally(message: str, counts: Counter[str]) -> None:
    """Update per-record-type counters from one raw frame."""
    counts["total"] += 1
    try:
        event = json.loads(message)
    except json.JSONDecodeError:
        counts["unparseable"] += 1
        return
    commit = event.get("commit")
    if not isinstance(commit, dict):
        return
    record_type = constants.COLLECTIONS.get(commit.get("collection", ""))
    if record_type:
        counts[record_type] += 1


async def _drain(socket: Any, handle: Any, counts: Counter[str], deadline: float) -> None:
    """Write frames verbatim to ``handle`` until ``deadline``, tallying as we go."""
    started = time.monotonic()
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            message = await asyncio.wait_for(socket.recv(), timeout=remaining)
        except TimeoutError:
            return

        text = message if isinstance(message, str) else message.decode("utf-8")
        handle.write(text)
        handle.write("\n")
        _tally(text, counts)

        if counts["total"] % 20_000 == 0:
            rate = counts["total"] / max(time.monotonic() - started, 1e-9)
            print(f"  {counts['total']:,} events  {rate:,.0f}/s")


async def capture(seconds: int, output_path: Path) -> dict[str, int]:
    """Stream Jetstream for ``seconds`` and write raw events as gzipped JSONL.

    Returns a per-record-type count. Events are written exactly as received so
    the replay stage owns all parsing -- a schema change should never require
    re-capturing.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    endpoint = build_endpoint()
    counts: Counter[str] = Counter()
    started = time.monotonic()

    print(f"connecting to {endpoint}")
    print(f"capturing for {seconds}s -> {output_path}")

    # max_size=None: some posts with large embeds exceed the 1MiB default frame cap.
    async with websockets.connect(endpoint, max_size=None) as socket:
        with gzip.open(output_path, "wt", encoding="utf-8") as handle:
            await _drain(socket, handle, counts, started + seconds)

    counts["elapsed_seconds"] = int(time.monotonic() - started)
    return dict(counts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture Bluesky Jetstream to a local file.")
    parser.add_argument("--seconds", type=int, default=constants.DEFAULT_CAPTURE_SECONDS)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    output_path = args.output or CAPTURE_DIR / f"jetstream-{stamp}.jsonl.gz"

    counts = asyncio.run(capture(args.seconds, output_path))

    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"\ncaptured {counts.get('total', 0):,} events in {counts.get('elapsed_seconds', 0)}s")
    for record_type in constants.RECORD_TYPES:
        print(f"  {record_type:<10} {counts.get(record_type, 0):>10,}")
    print(f"compressed size: {size_mb:.1f} MiB")
    print(f"wrote {output_path}")

    metadata_path = output_path.with_suffix(".meta.json")
    metadata_path.write_text(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
