"""Rejects requests that skipped CloudFront, which adds the shared secret header."""

from __future__ import annotations

import os
import secrets
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

SECRET_VARIABLE = "ORIGIN_SECRET"
HEADER = "X-Origin-Secret"
# Railway's healthcheck calls the origin directly.
EXEMPT_PATHS = {"/health"}


async def require_origin_secret(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    expected = os.getenv(SECRET_VARIABLE)
    if expected and request.url.path not in EXEMPT_PATHS:
        provided = request.headers.get(HEADER, "")
        if not secrets.compare_digest(provided.encode(), expected.encode()):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)
