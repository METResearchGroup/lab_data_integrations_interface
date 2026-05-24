"""Generate mock Bluesky-shaped Parquet data for database benchmark experiments.

Run from repo root:
    PYTHONPATH=. uv run python experiments/database_experiments_2026_05_23/random_data_generator.py --seed 42
    PYTHONPATH=. uv run python experiments/database_experiments_2026_05_23/random_data_generator.py --validate
    PYTHONPATH=. uv run python experiments/database_experiments_2026_05_23/random_data_generator.py --seed 42 --scale smoke
"""

from __future__ import annotations

import argparse
import random
import re
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from faker import Faker

from experiments.database_experiments_2026_05_23.config import FULL_CAPS, SMOKE_CAPS, ScaleCaps
from experiments.database_experiments_2026_05_23.date_utils import days_ago, format_created_at, parse_created_at
from experiments.database_experiments_2026_05_23.models import FollowModel, LikeModel, PostModel, UserModel
from lib.timestamp_utils import CREATED_AT_FORMAT

DEFAULT_OUTPUT_DIR = Path("experiments/database_experiments_2026_05_23/mock_data")
TABLES = ("user", "post", "like", "follow")
CREATED_AT_PATTERN = re.compile(r"^\d{4}_\d{2}_\d{2}-\d{2}:\d{2}:\d{2}$")


def generate_users(n: int, faker: Faker, rng: random.Random) -> list[UserModel]:
    users: list[UserModel] = []
    earliest = days_ago(180)
    latest = days_ago(30)
    window_seconds = int((latest - earliest).total_seconds())

    for _ in range(n):
        offset = rng.randint(0, window_seconds)
        created_at = format_created_at(earliest + timedelta(seconds=offset))
        users.append(
            UserModel(
                user_id=str(uuid.uuid4()),
                created_at=created_at,
            )
        )
    return users


def generate_posts(
    users: list[UserModel],
    faker: Faker,
    rng: random.Random,
    np_rng: np.random.Generator,
    max_posts: int,
) -> list[PostModel]:
    posts: list[PostModel] = []
    three_days_ago = days_ago(3)

    for user in users:
        count = max(0, int(np_rng.normal(loc=100, scale=5)))
        user_created = parse_created_at(user.created_at)
        window_start = user_created
        window_end = three_days_ago
        if window_start >= window_end:
            continue

        window_seconds = int((window_end - window_start).total_seconds())
        for _ in range(count):
            if len(posts) >= max_posts:
                return posts
            offset = rng.randint(0, window_seconds)
            created_at = format_created_at(window_start + timedelta(seconds=offset))
            posts.append(
                PostModel(
                    post_id=str(uuid.uuid4()),
                    author_id=user.user_id,
                    created_at=created_at,
                    text=faker.paragraph(nb_sentences=3),
                )
            )
    return posts


def generate_likes(
    users: list[UserModel],
    posts: list[PostModel],
    rng: random.Random,
    np_rng: np.random.Generator,
    max_likes: int,
) -> list[LikeModel]:
    likes: list[LikeModel] = []
    three_days_ago = days_ago(3)
    posts_by_id = {post.post_id: post for post in posts}

    for user in users:
        count = max(0, int(np_rng.normal(loc=200, scale=5)))
        eligible_posts = [post for post in posts if post.author_id != user.user_id]
        if not eligible_posts:
            continue

        sample_size = min(count, len(eligible_posts))
        sampled_posts = rng.sample(eligible_posts, k=sample_size)
        user_created = parse_created_at(user.created_at)

        for post in sampled_posts:
            if len(likes) >= max_likes:
                return likes
            post_created = parse_created_at(post.created_at)
            window_start = max(user_created, post_created)
            if window_start >= three_days_ago:
                continue
            window_seconds = int((three_days_ago - window_start).total_seconds())
            offset = rng.randint(0, window_seconds)
            likes.append(
                LikeModel(
                    like_id=str(uuid.uuid4()),
                    author_id=user.user_id,
                    post_id=post.post_id,
                    created_at=format_created_at(window_start + timedelta(seconds=offset)),
                )
            )
    return likes


def generate_follows(
    users: list[UserModel],
    rng: random.Random,
    max_follows: int,
) -> list[FollowModel]:
    seen: set[tuple[str, str]] = set()

    for follower in users:
        for followee in users:
            if follower.user_id == followee.user_id:
                continue
            if rng.random() >= 0.001:
                continue
            pair = (follower.user_id, followee.user_id)
            if pair in seen:
                continue
            seen.add(pair)
            if len(seen) >= max_follows:
                break
        if len(seen) >= max_follows:
            break

    return [FollowModel(follower_id=a, followee_id=b) for a, b in seen]


def write_parquet(records: list, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([record.model_dump() for record in records])
    frame.to_parquet(output_path, index=False)


def generate_all(
    output_dir: Path,
    caps: ScaleCaps,
    seed: int,
) -> dict[str, int]:
    faker = Faker()
    Faker.seed(seed)
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    users = generate_users(caps.users, faker, rng)
    posts = generate_posts(users, faker, rng, np_rng, caps.posts)
    likes = generate_likes(users, posts, rng, np_rng, caps.likes)
    follows = generate_follows(users, rng, caps.follows)

    write_parquet(users, output_dir / "user.parquet")
    write_parquet(posts, output_dir / "post.parquet")
    write_parquet(likes, output_dir / "like.parquet")
    write_parquet(follows, output_dir / "follow.parquet")

    counts = {
        "user": len(users),
        "post": len(posts),
        "like": len(likes),
        "follow": len(follows),
    }
    print(f"Generated mock data in {output_dir}: {counts}")
    return counts


def _validate_created_at(values: pd.Series, label: str) -> None:
    bad = values[~values.astype(str).str.match(CREATED_AT_PATTERN)]
    if not bad.empty:
        raise ValueError(f"{label} has invalid created_at format: {bad.iloc[0]}")


def validate_mock_data(mock_data_dir: Path, caps: ScaleCaps | None = None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in TABLES:
        path = mock_data_dir / f"{table}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Missing parquet file: {path}")
        frame = pq.read_table(path).to_pandas()
        counts[table] = len(frame)

    if caps is not None:
        if counts["user"] > caps.users:
            raise ValueError(f"user count {counts['user']} exceeds cap {caps.users}")
        if counts["post"] > caps.posts:
            raise ValueError(f"post count {counts['post']} exceeds cap {caps.posts}")
        if counts["like"] > caps.likes:
            raise ValueError(f"like count {counts['like']} exceeds cap {caps.likes}")
        if counts["follow"] > caps.follows:
            raise ValueError(f"follow count {counts['follow']} exceeds cap {caps.follows}")

    users = pq.read_table(mock_data_dir / "user.parquet").to_pandas()
    posts = pq.read_table(mock_data_dir / "post.parquet").to_pandas()
    likes = pq.read_table(mock_data_dir / "like.parquet").to_pandas()
    follows = pq.read_table(mock_data_dir / "follow.parquet").to_pandas()

    _validate_created_at(users["created_at"], "user")
    _validate_created_at(posts["created_at"], "post")
    _validate_created_at(likes["created_at"], "like")

    if users["user_id"].duplicated().any():
        raise ValueError("Duplicate user_id values found")
    if posts["post_id"].duplicated().any():
        raise ValueError("Duplicate post_id values found")
    if likes["like_id"].duplicated().any():
        raise ValueError("Duplicate like_id values found")

    posts_by_id = posts.set_index("post_id")
    merged = likes.merge(posts_by_id[["author_id"]], left_on="post_id", right_index=True, suffixes=("", "_post"))
    self_likes = merged[merged["author_id"] == merged["author_id_post"]]
    if not self_likes.empty:
        raise ValueError(f"Found {len(self_likes)} self-likes")

    follow_pairs = follows[["follower_id", "followee_id"]].apply(tuple, axis=1)
    if follow_pairs.duplicated().any():
        raise ValueError("Duplicate follow pairs found")

    print(f"Row counts: {counts}")
    print(f"created_at format: {CREATED_AT_FORMAT}")
    print("VALIDATION PASS")
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate or validate mock benchmark Parquet data")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scale", choices=("smoke", "full"), default="full")
    parser.add_argument("--mock-data-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--validate", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    caps = SMOKE_CAPS if args.scale == "smoke" else FULL_CAPS

    if args.validate:
        validate_mock_data(args.mock_data_dir, caps=None)
        return

    generate_all(args.mock_data_dir, caps, args.seed)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
