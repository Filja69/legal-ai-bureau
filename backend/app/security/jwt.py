"""JWT access-token encode/decode — Phase 7 brief §3. `python-jose` is the
only library touching tokens; no code outside this module ever inspects a
raw JWT string.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config.settings import Settings


class TokenError(Exception):
    """Any token problem (expired, bad signature, wrong issuer/audience,
    malformed) — callers always fail closed on this, never fall back to
    an unauthenticated identity."""


def encode_access_token(user_id: uuid.UUID, settings: Settings, *, expires_minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    expires_delta = timedelta(minutes=expires_minutes if expires_minutes is not None else settings.jwt_expires_minutes)
    claims = {
        "sub": str(user_id),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> dict:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except JWTError as exc:
        raise TokenError(str(exc)) from exc
