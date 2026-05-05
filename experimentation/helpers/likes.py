import asyncio
import json

import websockets
from atproto import Client
from experimentation.constants import JETSTREAM_URL, LIKE_COLLECTION, LIKES_TO_FETCH, STREAM_IDLE_TIMEOUT


def fetch_liked_post(client: Client, post_uri: str) -> dict:
    response = client.app.bsky.feed.get_posts({"uris": [post_uri]})
    if not response.posts:
        return {}
    post = response.posts[0]
    return {
        "author": post.author.handle,
        "text": getattr(post.record, "text", ""),
        "created_at": getattr(post.record, "created_at", ""),
        "uri": post.uri,
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


def reverse_likes(likes: list[dict]) -> list[dict]:
    return list(reversed(likes))


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
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=STREAM_IDLE_TIMEOUT)
                event = json.loads(raw)
                if is_like_create_event(event):
                    likes.append(event)
            except (TimeoutError, websockets.exceptions.ConnectionClosedError):
                break

    # jetstream will return least recent first, so need to reverse
    return reverse_likes(likes)[:LIKES_TO_FETCH]
