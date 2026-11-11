import time

import pytest

from intervue_security import (
    FileValidationError,
    RateLimiter,
    TokenError,
    decode_token,
    encode_token,
    hash_password,
    sign_path,
    validate_upload,
    verify_password,
    verify_signature,
)
from intervue_security.files import DOCUMENT_TYPES, IMAGE_TYPES

from .conftest import make_docx


def test_password_hashing_roundtrip():
    h = hash_password("correct horse battery")
    assert h != "correct horse battery" and h.startswith("$argon2")
    assert verify_password(h, "correct horse battery")
    assert not verify_password(h, "wrong")
    with pytest.raises(ValueError):
        hash_password("short")


def test_tokens_purpose_and_expiry():
    t = encode_token("s" * 40, "user-1", "session", 60)
    assert decode_token("s" * 40, t, "session")["sub"] == "user-1"
    with pytest.raises(TokenError):
        decode_token("s" * 40, t, "ws")  # wrong purpose
    with pytest.raises(TokenError):
        decode_token("x" * 40, t, "session")  # wrong secret
    expired = encode_token("s" * 40, "u", "session", -5)
    with pytest.raises(TokenError):
        decode_token("s" * 40, expired, "session")


def test_signed_urls():
    exp, sig = sign_path("secret", "resumes/a.pdf", 60)
    assert verify_signature("secret", "resumes/a.pdf", exp, sig)
    assert not verify_signature("secret", "resumes/b.pdf", exp, sig)
    assert not verify_signature("secret", "resumes/a.pdf", int(time.time()) - 1, sig)


def test_file_validation_sniffs_content():
    pdf = b"%PDF-1.4\n%fake but valid header\n"
    assert validate_upload("cv.pdf", pdf, DOCUMENT_TYPES, 1024).mime_type == "application/pdf"
    assert validate_upload("cv.docx", make_docx(["hello"]), DOCUMENT_TYPES, 10**6).extension == ".docx"
    with pytest.raises(FileValidationError):
        validate_upload("cv.pdf", b"MZ\x90\x00 executable", DOCUMENT_TYPES, 1024)  # disguised exe
    with pytest.raises(FileValidationError):
        validate_upload("cv.exe", pdf, DOCUMENT_TYPES, 1024)
    with pytest.raises(FileValidationError):
        validate_upload("cv.pdf", pdf * 100, DOCUMENT_TYPES, 50)  # too large
    with pytest.raises(FileValidationError):
        validate_upload("shot.png", pdf, IMAGE_TYPES, 1024)
    assert validate_upload("../../etc/passwd.pdf", pdf, DOCUMENT_TYPES, 1024).filename == "passwd.pdf"


def test_rate_limiter():
    rl = RateLimiter()
    assert all(rl.hit("k", 3, 60)[0] for _ in range(3))
    ok, retry = rl.hit("k", 3, 60)
    assert not ok and retry > 0
