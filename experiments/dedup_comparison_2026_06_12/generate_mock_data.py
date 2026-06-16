"""Generate mock AT Protocol URIs for the dedup benchmark.

Generates one large pool of unique URIs, then slices it into:
- Batch files: uris_100.txt, uris_1000.txt, uris_5000.txt, uris_10000.txt
- Seed files: uris_seed_10k.txt, uris_seed_100k.txt, uris_seed_1m.txt

All files are disjoint — no URI appears in more than one file.

Run from repo root:
    PYTHONPATH=. uv run python experiments/dedup_comparison_2026_06_12/generate_mock_data.py
"""

from __future__ import annotations

import random
import string
from pathlib import Path

MOCK_DATA_DIR = Path(__file__).parent / "mock_data"

BATCH_SIZES = [100, 1_000, 5_000, 10_000]
SEED_SIZES = [10_000, 100_000, 1_000_000]

TOTAL_NEEDED = sum(BATCH_SIZES) + sum(SEED_SIZES)


def _random_did(rng: random.Random) -> str:
    chars = string.ascii_lowercase + string.digits
    return "did:plc:" + "".join(rng.choices(chars, k=12))


def _random_rkey(rng: random.Random) -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(rng.choices(chars, k=13))


def generate_uri_pool(n: int, *, seed: int = 42) -> list[str]:
    rng = random.Random(seed)
    seen: set[str] = set()
    uris: list[str] = []
    while len(uris) < n:
        uri = f"at://{_random_did(rng)}/app.bsky.feed.post/{_random_rkey(rng)}"
        if uri not in seen:
            seen.add(uri)
            uris.append(uri)
    return uris


def write_uris(path: Path, uris: list[str]) -> None:
    path.write_text("\n".join(uris) + "\n", encoding="utf-8")
    print(f"  wrote {len(uris):>9,} URIs → {path.relative_to(Path(__file__).parents[2])}")


def main() -> None:
    MOCK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating {TOTAL_NEEDED:,} unique URIs...")
    pool = generate_uri_pool(TOTAL_NEEDED)

    offset = 0

    print("Writing batch files:")
    for n in BATCH_SIZES:
        write_uris(MOCK_DATA_DIR / f"uris_{n}.txt", pool[offset : offset + n])
        offset += n

    print("Writing seed files:")
    for n in SEED_SIZES:
        label = f"{n // 1000}k" if n < 1_000_000 else "1m"
        write_uris(MOCK_DATA_DIR / f"uris_seed_{label}.txt", pool[offset : offset + n])
        offset += n

    print(f"Done. Total URIs generated: {offset:,}")


if __name__ == "__main__":
    main()
