"""Who is calling, per the Supabase access token the UI forwards."""

from __future__ import annotations

import functools
import logging
import math
import os
import threading
import time

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWK, PyJWKClient

logger = logging.getLogger(__name__)

URL_VARIABLE = "SUPABASE_URL"

ALGORITHMS = ["ES256"]
AUDIENCE = "authenticated"

# Unknown kids refetch at most this often, so forged kids can't flood Supabase.
REFRESH_INTERVAL_SECONDS = 60

_last_refresh = -math.inf
_refresh_lock = threading.Lock()


@functools.lru_cache(maxsize=1)
def _jwk_client() -> PyJWKClient:
    url = os.getenv(URL_VARIABLE)
    if not url:
        raise RuntimeError(f"{URL_VARIABLE} is unset, so access tokens cannot be verified")

    return PyJWKClient(f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json")


def _may_refresh() -> bool:
    global _last_refresh
    with _refresh_lock:
        now = time.monotonic()
        if now - _last_refresh < REFRESH_INTERVAL_SECONDS:
            return False
        _last_refresh = now
        return True


def _signing_key(kid: str) -> PyJWK | None:
    client = _jwk_client()
    key = PyJWKClient.match_kid(client.get_signing_keys(), kid)
    if key is None and _may_refresh():
        # Possibly a key Supabase rotated in after our last fetch.
        key = PyJWKClient.match_kid(client.get_signing_keys(refresh=True), kid)
    return key


def current_user_email(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
) -> str:
    token = credentials.credentials
    try:
        kid = jwt.get_unverified_header(token).get("kid")
        signing_key = _signing_key(kid) if kid else None
        if signing_key is None:
            raise jwt.InvalidTokenError(f"unknown signing key {kid!r}")
        # Signature, expiry and audience.
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=ALGORITHMS,
            audience=AUDIENCE,
            options={"require": ["exp", "aud"]},
        )
    except jwt.PyJWTError as error:
        # Forged, expired or malformed.
        logger.info("rejected access token: %s", error)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        ) from error

    email = claims.get("email")
    if not email:
        # Signed by Supabase, but no address to mail results to.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token carries no email",
        )

    return email
