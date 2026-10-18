"""Token verification, against a locally generated P-256 key."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from backend import auth

EMAIL = "someone@example.invalid"


@pytest.fixture(scope="module")
def signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(autouse=True)
def jwks(monkeypatch: pytest.MonkeyPatch, signing_key):
    """Serve the matching public key instead of fetching Supabase's JWKS."""

    class FakeKey:
        key = signing_key.public_key()

    class FakeClient:
        def get_signing_key_from_jwt(self, _token):
            return FakeKey()

    monkeypatch.setattr(auth, "_jwk_client", lambda: FakeClient())


def _token(signing_key, **overrides) -> str:
    claims = {
        "email": EMAIL,
        "aud": auth.AUDIENCE,
        "exp": datetime.now(UTC) + timedelta(hours=1),
    } | overrides
    return jwt.encode(claims, signing_key, algorithm="ES256")


def _verify(token: str) -> str:
    return auth.current_user_email(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))


def test_valid_token_yields_the_email(signing_key) -> None:
    assert _verify(_token(signing_key)) == EMAIL


def test_expired_token_is_rejected(signing_key) -> None:
    expired = _token(signing_key, exp=datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(HTTPException) as raised:
        _verify(expired)
    assert raised.value.status_code == 401


def test_wrong_audience_is_rejected(signing_key) -> None:
    with pytest.raises(HTTPException) as raised:
        _verify(_token(signing_key, aud="some-other-service"))
    assert raised.value.status_code == 401


def test_token_signed_by_another_key_is_rejected() -> None:
    """The signature is what stops a caller minting their own email claim."""

    attacker_key = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(HTTPException) as raised:
        _verify(_token(attacker_key, email="victim@example.invalid"))
    assert raised.value.status_code == 401


def test_token_without_an_email_is_rejected(signing_key) -> None:
    token = jwt.encode(
        {"aud": auth.AUDIENCE, "exp": datetime.now(UTC) + timedelta(hours=1)},
        signing_key,
        algorithm="ES256",
    )
    with pytest.raises(HTTPException) as raised:
        _verify(token)
    assert raised.value.status_code == 401
