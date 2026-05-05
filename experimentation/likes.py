import asyncio
import json

import websockets
from atproto import Client
from constants import JETSTREAM_URL, LIKE_COLLECTION, LIKES_TO_FETCH, TIMEOUT_PER_MESSAGE_SECONDS


def fetch_liked_post(client: Client, post_uri: str) -> dict:
    response = client.app.bsky.feed.get_posts({"uris": [post_uri]})
    if not response.posts:
        return {}
    post = response.posts[0]
    return {
        "author": post.author.handle,
        "text": getattr(post.record, "text", ""),
    }


def build_jetstream_url(did: str, cursor: int) -> str:
    return f"{JETSTREAM_URL}?wantedCollections={LIKE_COLLECTION}&wantedDids={did}&cursor={cursor}"


def is_like_create_event(event: dict) -> bool:
    commit = event.get("commit", {})
    return (
        event.get("kind") == "commit"
        and commit.get("collection") == LIKE_COLLECTION
        and commit.get("operation") == "create"
    )


def get_liked_posts(client: Client, like_events: list[dict]) -> list[dict]:
    liked_posts = []
    for event in like_events:
        post_uri = event["commit"]["record"]["subject"]["uri"]
        post = fetch_liked_post(client, post_uri)
        if post:
            liked_posts.append(post)
    return liked_posts


async def fetch_likes_from_jetstream(did: str, cursor: int) -> list[dict]:
    url = build_jetstream_url(did, cursor)
    likes = []

    async with websockets.connect(url) as ws:
        while len(likes) < LIKES_TO_FETCH:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT_PER_MESSAGE_SECONDS)
                event = json.loads(raw)
                if is_like_create_event(event):
                    likes.append(event)
            except TimeoutError:
                print(
                    f"No new events for {TIMEOUT_PER_MESSAGE_SECONDS}s, "
                    f"stopping with {len(likes)} likes found."
                )
                break

    return likes
