import csv
import os

import typer
from atproto import Client
from dotenv import load_dotenv

load_dotenv()

BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE")
BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")
CSV_COLUMNS = [
    "uri",
    "url",
    "author_handle",
    "text",
    "created_at",
    "like_count",
    "repost_count",
    "reply_count",
    "quote_count",
]


def get_csv_rows(response):
    rows = []
    for post in response.posts:
        # example post.uri: at://did:plc:abc123xyz/app.bsky.feed.post/3lc4k7abc2s2b
        # use .split("/") to turn into list, grab only the last element (record key aka unique id)
        rkey = post.uri.split("/")[-1]
        rows.append(
            {
                "uri": post.uri,
                "url": f"https://bsky.app/profile/{post.author.handle}/post/{rkey}",
                "author_handle": post.author.handle,
                "text": post.record.text,  # type: ignore[union-attr]
                "created_at": post.record.created_at,  # type: ignore[union-attr]
                "like_count": post.like_count,
                "repost_count": post.repost_count,
                "reply_count": post.reply_count,
                "quote_count": post.quote_count,
            }
        )
    return rows


def write_posts_to_csv(csv_rows, output_path):
    os.makedirs(output_path, exist_ok=True)
    out_file = os.path.join(output_path, "posts.csv")

    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"Wrote {len(csv_rows)} posts to {out_file}")


def main(
    handle: str = typer.Option(
        ..., help="Bluesky handle of the user to fetch posts from (e.g. user.bsky.social)"
    ),
    keyword: str = typer.Option(..., help="Keyword to search for in post text"),
    output_path: str = typer.Option(..., help="Directory to write posts.csv into"),
    limit: int = typer.Option(50, help="Maximum number of posts to collect"),
):
    client = Client()
    client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)

    response = client.app.bsky.feed.search_posts(
        params={
            "q": keyword,
            "author": handle,
            "limit": limit,
            "sort": "latest",
        }
    )

    csv_rows = get_csv_rows(response)
    write_posts_to_csv(csv_rows, output_path)


if __name__ == "__main__":
    typer.run(main)
