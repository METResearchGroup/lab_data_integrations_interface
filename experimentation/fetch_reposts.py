from atproto_client.exceptions import BadRequestError
from constants import TARGET_HANDLES
from interactions import create_client, resolve_did, write_csv
from reposts import fetch_reposts


def main() -> None:
    client = create_client()
    rows = []

    for handle in TARGET_HANDLES:
        did = resolve_did(client, handle)
        if did is None:
            continue

        try:
            reposts = fetch_reposts(client, did)
            for post in reposts:
                rows.append({"handle": handle, "post_handle": post["author"], "post": post["text"]})
        except BadRequestError as e:
            print(f"Skipping @{handle}: {e}")

    write_csv("reposts.csv", rows, fieldnames=["handle", "post_handle", "post"])


if __name__ == "__main__":
    main()
