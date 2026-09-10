"""Build public bsky.app post URLs from AT-URIs."""

from __future__ import annotations

AT_URI_PREFIX = "at://"
BSKY_POST_COLLECTION = "app.bsky.feed.post"
BSKY_PROFILE_POST_URL = "https://bsky.app/profile/{did}/post/{rkey}"


def bsky_post_url(uri: str | None) -> str | None:
    """Return the public bsky.app URL for an AT-URI post, if the URI is well formed.

    The profile slot uses the DID from the AT-URI. No handle lookup is required.

    Parameters
    ----------
    uri
        AT-URI such as ``at://did:plc:abc/app.bsky.feed.post/xyz``.

    Returns
    -------
    str or None
        ``https://bsky.app/profile/{did}/post/{rkey}``, or ``None`` when the
        URI is missing or is not an ``app.bsky.feed.post``.
    """

    if not uri or not uri.startswith(AT_URI_PREFIX):
        return None
    remainder = uri[len(AT_URI_PREFIX) :]
    parts = remainder.split("/")
    if len(parts) < 3:
        return None
    did, collection, rkey = parts[0], parts[1], parts[2]
    if collection != BSKY_POST_COLLECTION or not did or not rkey:
        return None
    return BSKY_PROFILE_POST_URL.format(did=did, rkey=rkey)
