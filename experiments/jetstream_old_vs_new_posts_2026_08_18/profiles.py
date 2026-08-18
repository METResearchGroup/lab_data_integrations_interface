"""Public AppView profile lookup for authors in a parquet sample."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from experiments.jetstream_old_vs_new_posts_2026_08_18.constants import APPVIEW_PROFILE_URL

_PROFILE_KEYS = ("did", "handle", "displayName", "description", "createdAt", "postsCount")


def fetch_profile(did: str) -> dict[str, Any]:
    url = f"{APPVIEW_PROFILE_URL}?{urllib.parse.urlencode({'actor': did})}"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        return {"did": did, "error": f"HTTP {error.code}"}
    except urllib.error.URLError as error:
        return {"did": did, "error": str(error.reason)}
    return {key: payload.get(key) for key in _PROFILE_KEYS}


def fetch_profiles(dids: list[str]) -> list[dict[str, Any]]:
    return [fetch_profile(did) for did in dids]
