from pathlib import Path

from atproto import Client
from atproto_client.exceptions import BadRequestError
from helpers.interactions import create_client, resolve_did, write_csv
from helpers.posts import fetch_posts

from experimentation.constants import TARGET_HANDLES


def collect_rows(client: Client, handles: list[str]) -> list[dict]:
    rows = []
    for handle in handles:
        did = resolve_did(client, handle)
        if did is None:
            continue
        try:
            posts = fetch_posts(client, did)
            for post in posts:
                rows.append(
                    {
                        "handle": handle,
                        "post": post["text"],
                        "post_timestamp": post["created_at"],
                        "post_id": post["uri"],
                    }
                )
        except BadRequestError as e:
            print(f"Skipping @{handle}: {e}")
    return rows


def main() -> None:
    client = create_client()

    rows = collect_rows(client, TARGET_HANDLES)

    write_csv(
        Path(__file__).parent / "posts.csv",
        rows,
        fieldnames=["handle", "post", "post_timestamp", "post_id"],
    )


if __name__ == "__main__":
    main()
