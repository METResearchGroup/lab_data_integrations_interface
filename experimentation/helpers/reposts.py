from atproto import Client
from experimentation.constants import REPOSTS_TO_FETCH


def fetch_reposts(client: Client, did: str) -> list[dict]:
    reposts = []
    cursor = None

    while len(reposts) < REPOSTS_TO_FETCH:
        response = client.app.bsky.feed.get_author_feed(
            {"actor": did, "limit": 100, "cursor": cursor}
        )

        for item in response.feed:
            if item.reason is not None:
                reposts.append(
                    {
                        "author": item.post.author.handle,
                        "text": getattr(item.post.record, "text", ""),
                        "created_at": getattr(item.post.record, "created_at", ""),
                        "uri": item.post.uri,
                    }
                )
                if len(reposts) == REPOSTS_TO_FETCH:
                    break

        cursor = response.cursor
        if not cursor:
            break

    return reposts
