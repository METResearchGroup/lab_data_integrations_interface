import asyncio
import json
import os
import time

import websockets
from atproto import Client
from dotenv import load_dotenv

load_dotenv()

BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE")
BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")

TARGET_HANDLE = "zaffirorubino.bsky.social"

JETSTREAM_URL = "wss://jetstream2.us-east.bsky.network/subscribe"
REPOST_COLLECTION = "app.bsky.feed.repost"

HOURS_TO_LOOK_BACK = 48
SECONDS_PER_HOUR = 3600
MICROSECONDS_PER_SECOND = 1_000_000
REPOSTS_TO_FETCH = 10
TIMEOUT_PER_MESSAGE_SECONDS = 100000


def build_cursor(hours_back: int) -> int:
    seconds_back = hours_back * SECONDS_PER_HOUR
    return int((time.time() - seconds_back) * MICROSECONDS_PER_SECOND)


def build_jetstream_url(did: str, cursor: int) -> str:
    return (
        f"{JETSTREAM_URL}"
        f"?wantedCollections={REPOST_COLLECTION}"
        f"&wantedDids={did}"
        f"&cursor={cursor}"
    )


def is_repost_create_event(event: dict) -> bool:
    commit = event.get("commit", {})
    return (
        event.get("kind") == "commit"
        and commit.get("collection") == REPOST_COLLECTION
        and commit.get("operation") == "create"
    )


async def fetch_reposts_from_jetstream(did: str) -> list[dict]:
    cursor = build_cursor(HOURS_TO_LOOK_BACK)
    url = build_jetstream_url(did, cursor)
    reposts = []

    async with websockets.connect(url) as ws:
        while len(reposts) < REPOSTS_TO_FETCH:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT_PER_MESSAGE_SECONDS)
                event = json.loads(raw)
                if is_repost_create_event(event):
                    reposts.append(event)
            except asyncio.TimeoutError:
                print(f"No new events for {TIMEOUT_PER_MESSAGE_SECONDS}s, stopping with {len(reposts)} reposts found.")
                break

    return reposts


def get_reposted_posts(client: Client, repost_events: list[dict]) -> list[dict]:
    reposted_posts = []
    for event in repost_events:
        post_uri = event["commit"]["record"]["subject"]["uri"]
        post = fetch_post(client, post_uri)
        if post:
            reposted_posts.append(post)
    return reposted_posts


def fetch_post(client: Client, post_uri: str) -> dict:
    response = client.app.bsky.feed.get_posts({"uris": [post_uri]})
    if not response.posts:
        return {}
    post = response.posts[0]
    return {
        "author": post.author.handle,
        "text": getattr(post.record, "text", ""),
    }


def show_reposted_posts(reposted_posts: list[dict]) -> None:
    print(f"Last {len(reposted_posts)} reposted posts:\n")
    for i, post in enumerate(reposted_posts):
        print(f"{i + 1}: @{post['author']}: {post['text'][:120]!r}")
    print()


async def main() -> None:
    client = Client()
    client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)

    profile = client.app.bsky.actor.get_profile({"actor": TARGET_HANDLE})
    did = profile.did
    print(f"FETCHING LAST {REPOSTS_TO_FETCH} REPOSTS FOR @{TARGET_HANDLE}\n")

    repost_events = await fetch_reposts_from_jetstream(did)

    reposted_posts = get_reposted_posts(client, repost_events)
    show_reposted_posts(reposted_posts)


if __name__ == "__main__":
    asyncio.run(main())
