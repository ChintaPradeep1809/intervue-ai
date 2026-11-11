from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.deps import DB, SESSION_COOKIE, CurrentUser, client_ip
from app.models import CandidateProfile, Interview, JobDescription, Resume
from app.services.audit import audit
from app.services.storage import get_storage
from intervue_engine import ROLES

router = APIRouter(prefix="/api/me", tags=["profile"])


class ProfileIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    experience_years: float | None = Field(default=None, ge=0, le=50)
    target_role: str | None = None
    headline: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=120)
    onboarding_completed: bool | None = None
    preferences: dict[str, Any] | None = None


def profile_out(p: CandidateProfile, full_name: str, email: str) -> dict[str, Any]:
    return {
        "full_name": full_name,
        "email": email,
        "experience_years": p.experience_years,
        "target_role": p.target_role,
        "headline": p.headline,
        "location": p.location,
        "onboarding_completed": p.onboarding_completed,
        "preferences": p.preferences,
    }


async def _profile(db: DB, user: CurrentUser) -> CandidateProfile:
    p = (await db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id))).scalar_one_or_none()
    if p is None:
        p = CandidateProfile(user_id=user.id)
        db.add(p)
        await db.flush()
    return p


@router.get("/profile")
async def get_profile(user: CurrentUser, db: DB) -> dict[str, Any]:
    p = await _profile(db, user)
    await db.commit()
    resumes = (await db.execute(select(Resume).where(Resume.user_id == user.id).order_by(Resume.created_at.desc()))).scalars().all()
    return {
        **profile_out(p, user.full_name, user.email),
        "resumes": [{"id": str(r.id), "filename": r.filename, "size_bytes": r.size_bytes, "created_at": r.created_at} for r in resumes],
    }


@router.put("/profile")
async def update_profile(body: ProfileIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    p = await _profile(db, user)
    if body.target_role is not None and body.target_role not in ROLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown role.")
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    for field in ("experience_years", "target_role", "headline", "location", "onboarding_completed", "preferences"):
        v = getattr(body, field)
        if v is not None:
            setattr(p, field, v)
    await db.commit()
    return profile_out(p, user.full_name, user.email)


@router.delete("")
async def delete_account(request: Request, user: CurrentUser, db: DB) -> dict[str, Any]:
    """Privacy: delete the candidate's account and all their interviews, documents and transcripts."""
    if user.role == "super_admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Super admin accounts cannot be self-deleted.")
    storage = get_storage()
    for r in (await db.execute(select(Resume).where(Resume.user_id == user.id))).scalars():
        await storage.delete(r.storage_key)
    audit(db, "user.delete", None, ip=client_ip(request), deleted_user=str(user.id))
    await db.execute(delete(Interview).where(Interview.candidate_id == user.id))
    await db.execute(delete(JobDescription).where(JobDescription.user_id == user.id))
    await db.delete(user)
    await db.commit()
    from fastapi.responses import JSONResponse

    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp  # type: ignore[return-value]
