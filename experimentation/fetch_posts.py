from atproto_client.exceptions import BadRequestError
from constants import TARGET_HANDLES
from interactions import create_client, resolve_did, write_csv
from posts import fetch_posts


def main() -> None:
    client = create_client()
    rows = []

    for handle in TARGET_HANDLES:
        did = resolve_did(client, handle)
        if did is None:
            continue

        try:
            posts = fetch_posts(client, did)
            for post in posts:
                rows.append({"handle": handle, "post": post["text"]})
        except BadRequestError as e:
            print(f"Skipping @{handle}: {e}")

    write_csv("posts.csv", rows, fieldnames=["handle", "post"])


if __name__ == "__main__":
    main()
