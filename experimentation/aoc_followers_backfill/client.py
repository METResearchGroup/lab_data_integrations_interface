import os

from atproto import Client
from dotenv import load_dotenv

RELAY_BASE_URL = "https://bsky.network"


def create_client() -> Client:
    """Authenticated client against the entryway, for AppView queries
    (getFollowers, getProfiles, getAuthorFeed, resolveHandle, etc.)."""
    load_dotenv()
    client = Client()
    password = os.getenv("BLUESKY_PASSWORD") or os.getenv("BLUESKY_APP_PASSWORD")
    client.login(os.getenv("BLUESKY_HANDLE"), password)
    return client


def create_relay_client() -> Client:
    """Unauthenticated client against the relay, for getRepo.

    getRepo isn't proxied by the entryway (bsky.social) for arbitrary DIDs -
    it 404s as RepoNotFound unless the account happens to be on that specific
    PDS shard. The relay mirrors getRepo for the whole network, so it's the
    one endpoint that works for any DID regardless of where they're hosted.
    """
    return Client(base_url=RELAY_BASE_URL)
