from constants import POSTS_TO_FETCH, TARGET_HANDLES
from interactions import create_client, resolve_did, show_posts
from posts import fetch_posts


def main() -> None:
    client = create_client()

    for handle in TARGET_HANDLES:
        print(f"\n=== @{handle} ===\n")
        did = resolve_did(client, handle)

        print(f"FETCHING LAST {POSTS_TO_FETCH} POSTS FOR @{handle}\n")
        posts = fetch_posts(client, did)
        show_posts(posts, "posts")


if __name__ == "__main__":
    main()
