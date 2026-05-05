from constants import REPOSTS_TO_FETCH, TARGET_HANDLES
from interactions import create_client, resolve_did, show_posts
from reposts import fetch_repost_records, get_reposted_posts


def main() -> None:
    client = create_client()

    for handle in TARGET_HANDLES:
        print(f"\n=== @{handle} ===\n")
        did = resolve_did(client, handle)
        if did is None:
            continue

        print(f"FETCHING LAST {REPOSTS_TO_FETCH} REPOSTS FOR @{handle}\n")
        repost_records = fetch_repost_records(client, did)
        reposted_posts = get_reposted_posts(client, repost_records)
        show_posts(reposted_posts, "reposted posts")


if __name__ == "__main__":
    main()
