from atproto import Client
from constants import POSTS_TO_FETCH


def fetch_posts(client: Client, did: str) -> list[dict]:
    response = client.app.bsky.feed.get_author_feed(
        {
            "actor": did,
            "limit": POSTS_TO_FETCH,
            "filter": "posts_no_replies",
        }
    )
    return [
        {
            "author": item.post.author.handle,
            "text": getattr(item.post.record, "text", ""),
        }
        for item in response.feed
    ]
