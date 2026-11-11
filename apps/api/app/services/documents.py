"""Text extraction from uploaded documents. Files are parsed, never executed."""

from __future__ import annotations

import io

from intervue_security.files import DOCX_MIME, PDF_MIME, TXT_MIME

MAX_PAGES = 20
MAX_CHARS = 60_000


class ExtractionError(ValueError):
    pass


def extract_text(data: bytes, mime_type: str) -> str:
    try:
        if mime_type == PDF_MIME:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ExtractionError("Encrypted PDFs are not supported")
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PAGES])
        elif mime_type == DOCX_MIME:
            import docx

            d = docx.Document(io.BytesIO(data))
            parts = [p.text for p in d.paragraphs]
            for table in d.tables:
                for row in table.rows:
                    parts.append(" | ".join(c.text for c in row.cells))
            text = "\n".join(parts)
        elif mime_type == TXT_MIME:
            text = data.decode("utf-8", errors="replace")
        else:
            raise ExtractionError("Unsupported document type")
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError("Could not read the document. Please upload a text-based PDF or DOCX.") from exc
    text = "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
    return text[:MAX_CHARS]
