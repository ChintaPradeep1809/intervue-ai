from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import get_settings
from app.deps import DB, CurrentUser
from app.models import JobDescription, Resume
from app.services.audit import track
from app.services.documents import ExtractionError, extract_text
from app.services.storage import get_storage, new_key
from app.services.usage import flush, pricing, record, usage_scope
from intervue_engine import extract_skills
from intervue_security import FileValidationError, validate_upload, verify_signature
from intervue_security.files import DOCUMENT_TYPES

router = APIRouter(prefix="/api", tags=["documents"])


async def _read_validated(file: UploadFile) -> tuple[bytes, Any]:
    s = get_settings()
    data = await file.read(s.max_upload_mb * 1024 * 1024 + 1)
    try:
        v = validate_upload(file.filename or "", data, DOCUMENT_TYPES, s.max_upload_mb * 1024 * 1024)
    except FileValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return data, v


@router.post("/documents/resume", status_code=201)
async def upload_resume(user: CurrentUser, db: DB, file: UploadFile = File(...)) -> dict[str, Any]:
    data, v = await _read_validated(file)
    if v.extension == ".txt":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Please upload your resume as PDF or DOCX.")
    try:
        text = extract_text(data, v.mime_type)
    except ExtractionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if len(text.strip()) < 30:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "We couldn't find readable text in this file. Scanned images aren't supported yet.")
    key = new_key(f"resumes/{user.id}", v.extension)
    await get_storage().put(key, data, v.mime_type)
    resume = Resume(user_id=user.id, storage_key=key, filename=v.filename, mime_type=v.mime_type, size_bytes=v.size, text=text)
    db.add(resume)
    with usage_scope(user.id, None, None) as scope:
        record("storage", get_storage().name, v.size, pricing().storage_cost(v.size), task="resume")
        flush(db, scope)
    await db.commit()
    skills = extract_skills(text)
    return {
        "id": str(resume.id),
        "filename": resume.filename,
        "size_bytes": resume.size_bytes,
        "characters": len(text),
        "detected_skills": [s.name for s in skills],
    }


@router.get("/documents/resume/{resume_id}/url")
async def resume_url(resume_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, str]:
    from app.deps import can_view_interview
    from app.models import Interview

    r = await db.get(Resume, resume_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found.")
    if r.user_id != user.id:
        # org reviewers may view resumes attached to their org's interviews
        iv = (await db.execute(select(Interview).where(Interview.resume_id == r.id))).scalars().first()
        if iv is None or iv.candidate_id == user.id or not await can_view_interview(db, user, iv):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found.")
    return {"url": get_storage().signed_url(r.storage_key, 300)}


class JDIn(BaseModel):
    title: str = Field(default="", max_length=200)
    text: str = Field(min_length=20, max_length=30000)


@router.post("/documents/jd", status_code=201)
async def create_jd(body: JDIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    jd = JobDescription(user_id=user.id, title=body.title.strip(), text=body.text.strip(), source="paste")
    db.add(jd)
    await db.commit()
    return {"id": str(jd.id), "title": jd.title, "characters": len(jd.text), "detected_skills": [s.name for s in extract_skills(jd.text)]}


@router.post("/documents/jd/upload", status_code=201)
async def upload_jd(user: CurrentUser, db: DB, file: UploadFile = File(...), title: str = Form("")) -> dict[str, Any]:
    data, v = await _read_validated(file)
    try:
        text = extract_text(data, v.mime_type)
    except ExtractionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if len(text.strip()) < 20:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The job description file appears to be empty.")
    key = new_key(f"jds/{user.id}", v.extension)
    await get_storage().put(key, data, v.mime_type)
    jd = JobDescription(user_id=user.id, title=title.strip() or v.filename, text=text, source="upload", storage_key=key)
    db.add(jd)
    track(db, "jd_uploaded", user.id)
    await db.commit()
    return {"id": str(jd.id), "title": jd.title, "characters": len(text), "detected_skills": [s.name for s in extract_skills(text)]}


@router.get("/files/{key:path}")
async def serve_file(key: str, exp: int = Query(...), sig: str = Query(...)) -> RawResponse:
    if not verify_signature(get_settings().auth_secret, key, exp, sig):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This link has expired.")
    try:
        data = await get_storage().get(key)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.") from exc
    ext = key.rsplit(".", 1)[-1].lower()
    mime = {"pdf": "application/pdf", "docx": DOCUMENT_TYPES[".docx"], "jpg": "image/jpeg", "txt": "text/plain"}.get(ext, "application/octet-stream")
    return RawResponse(
        data,
        media_type=mime,
        headers={
            "Content-Disposition": f'inline; filename="document.{ext}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=60",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
