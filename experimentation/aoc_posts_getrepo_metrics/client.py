"""Unauthenticated Bluesky clients for public AppView and relay sync APIs."""

from atproto import Client

from experimentation.aoc_posts_getrepo_metrics.constants import (
    PUBLIC_APPVIEW_BASE_URL,
    RELAY_BASE_URL,
)


def create_public_client() -> Client:
    """Return an unauthenticated client for public AppView reads.

    Returns
    -------
    Client
        Client pointed at the public AppView host.
    """
    return Client(base_url=PUBLIC_APPVIEW_BASE_URL)


def create_relay_client() -> Client:
    """Return an unauthenticated client for relay ``getRepo`` calls.

    Returns
    -------
    Client
        Client pointed at the network relay host.
    """
    return Client(base_url=RELAY_BASE_URL)
