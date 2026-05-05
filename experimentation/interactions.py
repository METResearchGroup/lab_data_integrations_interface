import os
import time

from atproto import Client
from constants import MICROSECONDS_PER_SECOND, SECONDS_PER_HOUR
from dotenv import load_dotenv


def create_client() -> Client:
    load_dotenv()
    client = Client()
    client.login(os.getenv("BLUESKY_HANDLE"), os.getenv("BLUESKY_APP_PASSWORD"))
    return client


def resolve_did(client: Client, handle: str) -> str:
    return client.app.bsky.actor.get_profile({"actor": handle}).did


def build_cursor(hours_back: int) -> int:
    seconds_back = hours_back * SECONDS_PER_HOUR
    return int((time.time() - seconds_back) * MICROSECONDS_PER_SECOND)


def fetch_post(client: Client, post_uri: str) -> dict:
    response = client.app.bsky.feed.get_posts({"uris": [post_uri]})
    if not response.posts:
        return {}
    post = response.posts[0]
    return {
        "author": post.author.handle,
        "text": getattr(post.record, "text", ""),
    }


def show_posts(posts: list[dict], label: str) -> None:
    print(f"Last {len(posts)} {label}:\n")
    for i, post in enumerate(posts):
        print(f"{i + 1}: @{post['author']}: {post['text'][:120]!r}")
    print()
