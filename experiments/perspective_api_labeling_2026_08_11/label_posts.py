"""Label Bluesky posts with the Perspective API, flushing every N records.

Reads a posts Parquet file (e.g. data/2026-08-09.parquet), skips URIs already
present in labels/{date}.parquet (consolidated) and/or labels/tmp/{date}/,
then labels remaining posts in API batches. Safe to rerun after consolidating:
resume always dedupes against the consolidated file, not just tmp chunks.
Every FLUSH_SIZE labeled rows are written to
labels/tmp/{date}/{content_hash}.parquet.

Run from repo root:

    PYTHONPATH=. uv run python \\
        experiments/perspective_api_labeling_2026_08_11/label_posts.py \\
        data/2026-08-09.parquet

    PYTHONPATH=. uv run python \\
        experiments/perspective_api_labeling_2026_08_11/label_posts.py \\
        experiments/perspective_api_labeling_2026_08_11/data/2026-08-09.parquet \\
        --limit 1000
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import time
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from feature_generation.perspective_api.model import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DELAY_SECONDS,
    create_labels,
    create_perspective_request,
    process_perspective_batch_with_retries,
)
from feature_generation.perspective_api.schemas import PerspectiveApiLabelsModel
from lib.timestamp_utils import get_current_timestamp

EXPERIMENT_DIR = Path(__file__).resolve().parent
LABELS_DIR = EXPERIMENT_DIR / "labels"
FLUSH_SIZE = 10_000
EMPTY_TEXT_REASON = "Comment must be non-empty."


def empty_text_label(post: dict) -> dict:
    """Build a failed label row for posts with empty text (no API call)."""
    return PerspectiveApiLabelsModel(
        uri=post["uri"],
        text=post["text"],
        preprocessing_timestamp=post["preprocessing_timestamp"],
        was_successfully_labeled=False,
        reason=EMPTY_TEXT_REASON,
        label_timestamp=get_current_timestamp(),
    ).model_dump()


def resolve_date(posts_path: Path, date_arg: str | None) -> str:
    if date_arg:
        return date_arg
    stem = posts_path.stem
    # Expect YYYY-MM-DD from download_posts_by_day.py output filenames.
    if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
        return stem
    raise ValueError(f"Could not infer date from {posts_path.name}; pass --date YYYY-MM-DD")


def load_already_labeled_uris(tmp_dir: Path, date: str) -> set[str]:
    """Return URIs already labeled for this date.

    Sources (union, deduped):
    1. labels/{date}.parquet — consolidated file from prior runs
    2. labels/tmp/{date}/*.parquet — in-progress flush chunks

    Checking the consolidated file is required so reruns after
    consolidate_labels.py (which clears tmp) do not relabel the same posts.
    """
    uris: set[str] = set()
    consolidated = LABELS_DIR / f"{date}.parquet"
    if consolidated.exists():
        frame = pd.read_parquet(consolidated, columns=["uri"])
        from_cons = {str(uri) for uri in frame["uri"].tolist() if uri}
        uris.update(from_cons)
        print(f"skip uris from consolidated {consolidated.name}: {len(from_cons):,}")
    else:
        print(f"no consolidated labels at {consolidated.name}")

    if not tmp_dir.exists():
        return uris

    from_tmp = 0
    for path in sorted(tmp_dir.glob("*.parquet")):
        if path.name.startswith("."):
            continue
        frame = pd.read_parquet(path, columns=["uri"])
        before = len(uris)
        uris.update(str(uri) for uri in frame["uri"].tolist() if uri)
        from_tmp += len(uris) - before
    print(f"skip uris newly from tmp chunks: {from_tmp:,}")
    return uris


def posts_for_api(frame: pd.DataFrame) -> list[dict]:
    """Map Iceberg post rows to the shape expected by create_labels()."""
    posts: list[dict] = []
    for row in frame.itertuples(index=False):
        text = getattr(row, "text", None)
        uri = getattr(row, "uri", None)
        if uri is None or (isinstance(uri, float) and pd.isna(uri)):
            continue
        if text is None or (isinstance(text, float) and pd.isna(text)):
            text = ""
        created_at = getattr(row, "created_at", None)
        preprocessing_timestamp = (
            ""
            if created_at is None or (isinstance(created_at, float) and pd.isna(created_at))
            else str(created_at)
        )
        posts.append(
            {
                "uri": str(uri),
                "text": str(text),
                "preprocessing_timestamp": preprocessing_timestamp,
            }
        )
    return posts


def flush_labels(buffer: list[dict], tmp_dir: Path) -> tuple[Path, int]:
    """Write buffered labels to labels/tmp/{date}/{sha256_16}.parquet and clear buffer.

    Returns (output_path, rows_flushed).
    """
    if not buffer:
        raise ValueError("flush_labels called with empty buffer")

    rows_flushed = len(buffer)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(buffer)
    partial = (
        tmp_dir / f".partial-{hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:8]}.parquet"
    )
    frame.to_parquet(partial, index=False)

    digest = hashlib.sha256(partial.read_bytes()).hexdigest()[:16]
    output_path = tmp_dir / f"{digest}.parquet"
    if output_path.exists():
        # Content-identical flush already on disk; drop the partial.
        partial.unlink()
    else:
        partial.replace(output_path)

    buffer.clear()
    return output_path, rows_flushed


async def label_posts(
    posts: list[dict],
    *,
    tmp_dir: Path,
    batch_size: int,
    delay_seconds: float,
    flush_size: int,
) -> int:
    buffer: list[dict] = []
    labeled = 0

    with tqdm(total=len(posts), unit="post", desc="labeling") as progress:
        for start in range(0, len(posts), batch_size):
            batch = posts[start : start + batch_size]
            nonempty = [post for post in batch if post["text"].strip()]
            empty = [post for post in batch if not post["text"].strip()]

            labels: list[dict] = [empty_text_label(post) for post in empty]
            if nonempty:
                requests = [create_perspective_request(post["text"]) for post in nonempty]
                responses = await process_perspective_batch_with_retries(requests)
                labels.extend(create_labels(nonempty, responses))

            buffer.extend(labels)
            labeled += len(labels)

            if len(buffer) >= flush_size:
                output_path, rows_flushed = flush_labels(buffer, tmp_dir)
                progress.update(rows_flushed)
                progress.set_postfix_str(f"flushed {output_path.relative_to(EXPERIMENT_DIR)}")

            # Stay under Perspective QPS between batches (skip delay after last batch).
            if start + batch_size < len(posts) and nonempty:
                await asyncio.sleep(delay_seconds)

        if buffer:
            output_path, rows_flushed = flush_labels(buffer, tmp_dir)
            progress.update(rows_flushed)
            progress.set_postfix_str(f"flushed {output_path.relative_to(EXPERIMENT_DIR)}")

    return labeled


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Label posts Parquet with Perspective API, flushing every N rows."
    )
    parser.add_argument(
        "posts_parquet",
        type=Path,
        help="Path to posts Parquet (e.g. data/2026-08-09.parquet)",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Partition date YYYY-MM-DD (default: inferred from posts filename)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max number of unlabeled posts to process",
    )
    parser.add_argument(
        "--flush-size",
        type=int,
        default=FLUSH_SIZE,
        help=f"Flush buffer to Parquet after this many labels (default: {FLUSH_SIZE})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Perspective API batch size (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help=f"Delay between API batches (default: {DEFAULT_DELAY_SECONDS})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    posts_path = args.posts_parquet
    if not posts_path.is_absolute():
        # Allow paths relative to CWD or to the experiment directory.
        candidates = [Path.cwd() / posts_path, EXPERIMENT_DIR / posts_path]
        for candidate in candidates:
            if candidate.exists():
                posts_path = candidate
                break
    posts_path = posts_path.resolve()
    if not posts_path.exists():
        raise FileNotFoundError(f"Posts Parquet not found: {args.posts_parquet}")

    date = resolve_date(posts_path, args.date)
    tmp_dir = LABELS_DIR / "tmp" / date

    print(f"posts: {posts_path}")
    print(f"date: {date}")
    print(f"tmp dir: {tmp_dir}")

    already = load_already_labeled_uris(tmp_dir, date)
    print(f"already labeled: {len(already):,}")

    frame = pd.read_parquet(posts_path, columns=["uri", "text", "created_at"])
    if already:
        frame = frame[~frame["uri"].astype(str).isin(already)]
    if args.limit is not None:
        frame = frame.head(args.limit)

    posts = posts_for_api(frame)
    print(f"to label: {len(posts):,}")
    if not posts:
        print("nothing to do")
        return

    labeled = asyncio.run(
        label_posts(
            posts,
            tmp_dir=tmp_dir,
            batch_size=args.batch_size,
            delay_seconds=args.delay_seconds,
            flush_size=args.flush_size,
        )
    )
    print(f"done: labeled {labeled:,} posts into {tmp_dir}")


if __name__ == "__main__":
    main()
