from atproto import Client
from constants import REPOST_COLLECTION, REPOSTS_TO_FETCH
from interactions import fetch_post


def fetch_repost_records(client: Client, did: str) -> list:
    response = client.com.atproto.repo.list_records(
        {
            "repo": did,
            "collection": REPOST_COLLECTION,
            "limit": REPOSTS_TO_FETCH,
        }
    )
    return response.records


def get_reposted_posts(client: Client, repost_records: list) -> list[dict]:
    reposted_posts = []
    for record in repost_records:
        post_uri = record.value.subject.uri
        post = fetch_post(client, post_uri)
        if post:
            reposted_posts.append(post)
    return reposted_posts
