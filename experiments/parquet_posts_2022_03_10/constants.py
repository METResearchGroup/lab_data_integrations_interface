"""Paths and S3 location for the 2022-03-10 Iceberg posts file."""

from pathlib import Path

S3_URI = (
    "s3://lab-data-integrations-interface/bluesky/raw/posts/data/"
    "created_at_day=2022-03-10/"
    "00000-38-5a249a3c-fde3-4340-adbd-3a235f0fa83b.parquet"
)
BUCKET = "lab-data-integrations-interface"
KEY = (
    "bluesky/raw/posts/data/created_at_day=2022-03-10/"
    "00000-38-5a249a3c-fde3-4340-adbd-3a235f0fa83b.parquet"
)

EXPERIMENT_DIR = Path(__file__).resolve().parent
DATA_DIR = EXPERIMENT_DIR / "data"
PARQUET_PATH = DATA_DIR / "00000-38-5a249a3c-fde3-4340-adbd-3a235f0fa83b.parquet"
CSV_PATH = DATA_DIR / "posts.csv"
JSONL_PATH = DATA_DIR / "post_links.jsonl"

PUBLIC_APPVIEW_BASE_URL = "https://public.api.bsky.app"
GET_POSTS_MAX_URIS = 25
