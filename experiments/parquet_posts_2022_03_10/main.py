"""Convert one Iceberg posts parquet partition to CSV, hydrate via AppView, write links.

Run from the repo root:

    PYTHONPATH=. uv run python -m experiments.parquet_posts_2022_03_10.main
"""

from __future__ import annotations

import json
from typing import Any

import boto3
import pandas as pd
from atproto import Client

from experiments.parquet_posts_2022_03_10.constants import (
    BUCKET,
    CSV_PATH,
    DATA_DIR,
    GET_POSTS_MAX_URIS,
    JSONL_PATH,
    KEY,
    PARQUET_PATH,
    PUBLIC_APPVIEW_BASE_URL,
    S3_URI,
)


def _model_to_dict(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def download_parquet() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {S3_URI}")
    boto3.client("s3", region_name="us-east-2").download_file(BUCKET, KEY, str(PARQUET_PATH))


def parquet_to_csv() -> pd.DataFrame:
    df = pd.read_parquet(PARQUET_PATH)
    df.to_csv(CSV_PATH, index=False)
    print(f"Wrote {len(df)} rows to {CSV_PATH}")
    return df


def unique_uris(df: pd.DataFrame) -> list[str]:
    uris = [uri for uri in df["uri"].tolist() if isinstance(uri, str) and uri]
    return list(dict.fromkeys(uris))


def fetch_posts_by_uri(client: Client, uris: list[str]) -> dict[str, Any]:
    posts_by_uri: dict[str, Any] = {}
    for start in range(0, len(uris), GET_POSTS_MAX_URIS):
        batch = uris[start : start + GET_POSTS_MAX_URIS]
        response = client.app.bsky.feed.get_posts({"uris": batch})
        for post in response.posts:
            posts_by_uri[post.uri] = post
    return posts_by_uri


def post_url(post: Any) -> str:
    rkey = post.uri.split("/")[-1]
    return f"https://bsky.app/profile/{post.author.handle}/post/{rkey}"


def write_post_links(uris: list[str], posts_by_uri: dict[str, Any]) -> None:
    with JSONL_PATH.open("w", encoding="utf-8") as handle:
        for uri in uris:
            post = posts_by_uri.get(uri)
            if post is None:
                row = {
                    "uri": uri,
                    "found": False,
                    "url": None,
                    "cid": None,
                    "author_handle": None,
                    "author_did": None,
                    "record": None,
                }
            else:
                row = {
                    "uri": uri,
                    "found": True,
                    "url": post_url(post),
                    "cid": post.cid,
                    "author_handle": post.author.handle,
                    "author_did": post.author.did,
                    "record": _model_to_dict(post.record),
                }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(uris)} lines to {JSONL_PATH}")


def main() -> None:
    download_parquet()
    df = parquet_to_csv()
    uris = unique_uris(df)
    print(f"Unique post URIs: {len(uris)}")
    client = Client(base_url=PUBLIC_APPVIEW_BASE_URL)
    posts_by_uri = fetch_posts_by_uri(client, uris)
    print(f"AppView getPosts hits: {len(posts_by_uri)}")
    write_post_links(uris, posts_by_uri)


if __name__ == "__main__":
    main()
