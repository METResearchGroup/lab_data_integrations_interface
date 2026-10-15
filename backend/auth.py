"""Who is calling, per the Supabase access token the UI forwards."""

from __future__ import annotations

import functools
import logging
import os

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

URL_VARIABLE = "SUPABASE_URL"

ALGORITHMS = ["ES256"]
AUDIENCE = "authenticated"


@functools.lru_cache(maxsize=1)
def _jwk_client() -> PyJWKClient:
    url = os.getenv(URL_VARIABLE)
    if not url:
        raise RuntimeError(f"{URL_VARIABLE} is unset, so access tokens cannot be verified")

    return PyJWKClient(f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json")


def current_user_email(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
) -> str:
    token = credentials.credentials
    try:
        # Cached keys only: an unknown kid must not trigger a JWKS refetch.
        kid = jwt.get_unverified_header(token).get("kid")
        signing_key = kid and PyJWKClient.match_kid(_jwk_client().get_signing_keys(), kid)
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
