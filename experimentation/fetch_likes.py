import asyncio

from constants import HOURS_TO_LOOK_BACK, TARGET_HANDLES
from interactions import build_cursor, create_client, resolve_did, write_csv
from likes import fetch_likes_from_jetstream, get_liked_posts


async def main() -> None:
    client = create_client()
    cursor = build_cursor(HOURS_TO_LOOK_BACK)
    rows = []

    for handle in TARGET_HANDLES:
        did = resolve_did(client, handle)
        if did is None:
            continue

        like_events = await fetch_likes_from_jetstream(did, cursor)
        liked_posts = get_liked_posts(client, like_events)
        for post in liked_posts:
            rows.append({"handle": handle, "post_handle": post["author"], "post": post["text"]})

    write_csv("likes.csv", rows, fieldnames=["handle", "post_handle", "post"])


if __name__ == "__main__":
    asyncio.run(main())
