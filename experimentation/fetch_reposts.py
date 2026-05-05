from constants import TARGET_HANDLES
from interactions import create_client, resolve_did, write_csv
from reposts import fetch_repost_records, get_reposted_posts


def main() -> None:
    client = create_client()
    rows = []

    for handle in TARGET_HANDLES:
        did = resolve_did(client, handle)
        if did is None:
            continue

        repost_records = fetch_repost_records(client, did)
        reposted_posts = get_reposted_posts(client, repost_records)
        for post in reposted_posts:
            rows.append({"handle": handle, "post_handle": post["author"], "post": post["text"]})

    write_csv("reposts.csv", rows, fieldnames=["handle", "post_handle", "post"])


if __name__ == "__main__":
    main()
