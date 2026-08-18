"""Paths and the two example Iceberg data files to compare."""

from pathlib import Path

EXPERIMENT_ROOT = Path(__file__).parent
DATA_DIR = EXPERIMENT_ROOT / "data"
DOWNLOAD_DIR = DATA_DIR / "downloads"

AWS_REGION = "us-east-2"
S3_BUCKET = "lab-data-integrations-interface"

OLD_KEY = (
    "bluesky/raw/posts/data/created_at_day=2022-01-11/"
    "00000-171-7cae65fc-7cbd-4b54-8e2c-3b5834652eef.parquet"
)
NEW_KEY = (
    "bluesky/raw/posts/data/created_at_day=2026-08-18/"
    "00000-0-1205bc22-dd50-4bc2-b7e0-8023ebbe4a0c.parquet"
)

POSTS_DATA_PREFIX = "bluesky/raw/posts/data/"
INVENTORY_YEARS = (2021, 2022, 2023, 2024, 2025, 2026)

APPVIEW_PROFILE_URL = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile"

# ATProto TID alphabet (base32-sortable). Clock-id occupies the low 10 bits.
TID_ALPHABET = "234567abcdefghijklmnopqrstuvwxyz"
TID_CLOCK_ID_BITS = 10
