import asyncio
from pathlib import Path

from atproto import Client
from helpers.interactions import build_cursor, create_client, resolve_did, write_csv
from helpers.likes import fetch_liked_posts

from experimentation.constants import HOURS_TO_LOOK_BACK, TARGET_HANDLES


def map_dids_to_handles(client: Client, handles: list[str]) -> dict[str, str]:
    did_to_handle: dict[str, str] = {}
    for handle in handles:
        did = resolve_did(client, handle)
        if did is None:
            continue
        did_to_handle[did] = handle
    return did_to_handle


async def collect_rows(client: Client, handles: list[str], cursor: int) -> list[dict]:
    rows: list[dict] = []

    did_to_handle = map_dids_to_handles(client, handles)
    liked_posts_by_did = await fetch_liked_posts(client, list(did_to_handle.keys()), cursor)

    for did, posts in liked_posts_by_did.items():
        handle = did_to_handle[did]
        for post in posts:
            rows.append(
                {
                    "handle": handle,
                    "post_handle": post["author"],
                    "post": post["text"],
                    "post_timestamp": post["created_at"],
                    "post_id": post["uri"],
                }
            )

    return rows


async def main() -> None:
    client = create_client()
    cursor = build_cursor(HOURS_TO_LOOK_BACK)

    rows = await collect_rows(client, TARGET_HANDLES, cursor)
    write_csv(
        Path(__file__).parent / "likes2.csv",
        rows,
        fieldnames=["handle", "post_handle", "post", "post_timestamp", "post_id"],
    )


if __name__ == "__main__":
    asyncio.run(main())
