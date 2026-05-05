import asyncio

from constants import HOURS_TO_LOOK_BACK, LIKES_TO_FETCH, TARGET_HANDLES
from interactions import build_cursor, create_client, resolve_did, show_posts
from likes import fetch_likes_from_jetstream, get_liked_posts


async def main() -> None:
    client = create_client()
    cursor = build_cursor(HOURS_TO_LOOK_BACK)

    for handle in TARGET_HANDLES:
        print(f"\n=== @{handle} ===\n")
        did = resolve_did(client, handle)
        if did is None:
            continue

        print(f"FETCHING LAST {LIKES_TO_FETCH} LIKES FOR @{handle}\n")
        like_events = await fetch_likes_from_jetstream(did, cursor)
        liked_posts = get_liked_posts(client, like_events)
        show_posts(liked_posts, "liked posts")


if __name__ == "__main__":
    asyncio.run(main())
