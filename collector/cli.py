import os
import typer

from atproto import Client
from dotenv import load_dotenv

load_dotenv()

BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE")
BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")

def main(
    handle: str = typer.Option(..., help="Bluesky handle of the user to fetch posts from (e.g. user.bsky.social)"),
    keyword: str = typer.Option(..., help="Keyword to search for in post text"),
    output_path: str = typer.Option(..., help="Path to write the output CSV file"),
    limit: int = typer.Option(50, help="Maximum number of posts to collect"),
):
    client = Client()
    client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)
    
    response = client.app.bsky.feed.search_posts(
        params = {
            "q": keyword,
            "author": handle,
            "limit": limit,
            "sort": "latest",
        }
    )

    for post in response.posts:
        print(f"AUTHOR: {post.author.handle} CONTENT: {post.record.text}\n") # type: ignore[union-attr]
    
    if response.cursor:
        print(f"CURSOR: {response.cursor}")
    else:
        print("no response cursor :(")




if __name__ == "__main__":
    typer.run(main)
