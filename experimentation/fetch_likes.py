import asyncio
from pathlib import Path

from atproto_client.exceptions import BadRequestError
from constants import HOURS_TO_LOOK_BACK, TARGET_HANDLES
from helpers.interactions import build_cursor, create_client, resolve_did, write_csv
from helpers.likes import fetch_likes_from_jetstream, get_liked_posts


async def main() -> None:
    client = create_client()
    cursor = build_cursor(HOURS_TO_LOOK_BACK)
    rows = []

    for i, handle in enumerate(TARGET_HANDLES):
        did = resolve_did(client, handle)
        if did is None:
            continue

        try:
            like_events = await fetch_likes_from_jetstream(did, cursor)
            liked_posts = get_liked_posts(client, like_events)
            for post in liked_posts:
                rows.append(
                    {
                        "handle": handle,
                        "post_handle": post["author"],
                        "post": post["text"],
                        "post_timestamp": post["created_at"],
                        "post_id": post["uri"],
                    }
                )
        except BadRequestError as e:
            print(f"Skipping @{handle}: {e}")
        print(f"done with {i + 1} handles")

    write_csv(
        Path(__file__).parent / "likes.csv",
        rows,
        fieldnames=["handle", "post_handle", "post", "post_timestamp", "post_id"],
    )


if __name__ == "__main__":
    asyncio.run(main())
