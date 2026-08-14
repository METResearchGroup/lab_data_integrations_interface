from atproto import Client

RELAY_BASE_URL = "https://bsky.network"
PUBLIC_APPVIEW_BASE_URL = "https://public.api.bsky.app"


def create_public_client() -> Client:
    """Unauthenticated client against the public AppView mirror, for
    resolving handles to DIDs."""
    return Client(base_url=PUBLIC_APPVIEW_BASE_URL)


def create_relay_client() -> Client:
    """Unauthenticated client against the relay, for getRepo.

    getRepo isn't proxied by the entryway for arbitrary DIDs - it 404s as
    RepoNotFound unless the account is on that PDS shard. The relay mirrors
    getRepo for the whole network.
    """
    return Client(base_url=RELAY_BASE_URL)
