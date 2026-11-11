"""Signed JWTs for sessions and short-lived purpose tokens (WebSocket tickets, invites)."""

from __future__ import annotations

import time
import uuid
from typing import Any

import jwt

ALGORITHM = "HS256"


class TokenError(Exception):
    pass


def encode_token(
    secret: str,
    subject: str,
    purpose: str,
    ttl_seconds: int,
    extra: dict[str, Any] | None = None,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": subject,
        "pur": purpose,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(secret: str, token: str, purpose: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("expired") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("invalid") from exc
    if payload.get("pur") != purpose:
        raise TokenError("wrong purpose")
    return payload
