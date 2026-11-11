"""Upload validation: size, extension and content sniffing. Uploaded files are never executed."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TXT_MIME = "text/plain"
JPEG_MIME = "image/jpeg"
PNG_MIME = "image/png"
WEBP_MIME = "image/webp"

DOCUMENT_TYPES = {".pdf": PDF_MIME, ".docx": DOCX_MIME, ".txt": TXT_MIME}
IMAGE_TYPES = {".jpg": JPEG_MIME, ".jpeg": JPEG_MIME, ".png": PNG_MIME, ".webp": WEBP_MIME}


class FileValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedFile:
    filename: str
    extension: str
    mime_type: str
    size: int


def _sniff(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return PDF_MIME
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG_MIME
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG_MIME
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return WEBP_MIME
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())
        except zipfile.BadZipFile:
            return None
        if "word/document.xml" in names and "[Content_Types].xml" in names:
            return DOCX_MIME
        return None
    try:
        text = data[:4096].decode("utf-8")
    except UnicodeDecodeError:
        return None
    if "\x00" in text:
        return None
    return TXT_MIME


def validate_upload(
    filename: str,
    data: bytes,
    allowed: dict[str, str],
    max_bytes: int,
) -> ValidatedFile:
    name = (filename or "").strip().replace("\\", "/").split("/")[-1]
    if not name or "." not in name:
        raise FileValidationError("File must have an extension")
    ext = "." + name.rsplit(".", 1)[1].lower()
    if ext not in allowed:
        raise FileValidationError(f"Unsupported file type {ext}. Allowed: {', '.join(sorted(allowed))}")
    if not data:
        raise FileValidationError("File is empty")
    if len(data) > max_bytes:
        raise FileValidationError(f"File exceeds {max_bytes // (1024 * 1024)} MB limit")
    sniffed = _sniff(data)
    if sniffed != allowed[ext]:
        raise FileValidationError("File content does not match its extension")
    safe_name = "".join(c for c in name if c.isalnum() or c in "._- ")[:120] or f"upload{ext}"
    return ValidatedFile(filename=safe_name, extension=ext, mime_type=sniffed, size=len(data))
