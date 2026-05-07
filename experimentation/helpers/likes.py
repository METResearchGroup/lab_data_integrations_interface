import asyncio
import json

import websockets
from atproto import Client

from experimentation.constants import (
    JETSTREAM_URL,
    LIKE_COLLECTION,
    LIKES_TO_FETCH,
    STREAM_IDLE_TIMEOUT,
)


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


def build_jetstream_url(dids: list[str], cursor: int) -> str:
    wanted_dids = "&".join(f"wantedDids={did}" for did in dids)
    return f"{JETSTREAM_URL}?wantedCollections={LIKE_COLLECTION}&{wanted_dids}&cursor={cursor}"


def is_like_create_event(event: dict) -> bool:
    commit = event.get("commit", {})
    return (
        event.get("kind") == "commit"
        and commit.get("collection") == LIKE_COLLECTION
        and commit.get("operation") == "create"
    )


def collect_like_event(event: dict, did_to_events: dict[str, list[dict]]) -> None:
    if not is_like_create_event(event):
        return
    did = event.get("did") # did of the liker
    if did in did_to_events:
        did_to_events[did].append(event)



def get_liked_posts(client: Client, like_events: list[dict]) -> list[dict]:
    liked_posts = []
    for event in like_events:
        post_uri = event["commit"]["record"]["subject"]["uri"]
        post = fetch_liked_post(client, post_uri)
        if post:
            liked_posts.append(post)
    return liked_posts


async def fetch_liked_posts(client: Client, dids: list[str], cursor: int) -> dict[str, list[dict]]:
    url = build_jetstream_url(dids, cursor)
    did_to_events: dict[str, list[dict]] = {did: [] for did in dids}

    async with websockets.connect(url) as ws:
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=STREAM_IDLE_TIMEOUT)
                event = json.loads(raw)
                collect_like_event(event, did_to_events)
                print("collected an event")
            except (TimeoutError, websockets.exceptions.ConnectionClosedError):
                break

    return {
        did: get_liked_posts(client, list(reversed(events))[:LIKES_TO_FETCH])
        for did, events in did_to_events.items()
    }
