"""HMAC-signed, expiring URLs for the local storage backend (S3 uses native presigned URLs)."""

from __future__ import annotations

import hashlib
import hmac
import time


def _mac(secret: str, path: str, expires: int) -> str:
    msg = f"{path}:{expires}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def sign_path(secret: str, path: str, ttl_seconds: int = 300) -> tuple[int, str]:
    expires = int(time.time()) + ttl_seconds
    return expires, _mac(secret, path, expires)


def verify_signature(secret: str, path: str, expires: int, signature: str) -> bool:
    if expires < int(time.time()):
        return False
    return hmac.compare_digest(_mac(secret, path, expires), signature)
