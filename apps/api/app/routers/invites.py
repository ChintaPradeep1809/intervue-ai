from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.deps import DB, CurrentUser, client_ip
from app.models import Interview, InterviewTemplate, Invite, Organization, OrganizationMember, Resume
from app.routers.interviews import interview_detail
from app.services.audit import audit
from app.services.interviews import create_interview, enforce_limits
from intervue_engine import ROLES

router = APIRouter(prefix="/api/invites", tags=["invites"])


async def _valid_invite(db: DB, token: str) -> tuple[Invite, InterviewTemplate, Organization]:
    inv = (await db.execute(select(Invite).where(Invite.token == token))).scalar_one_or_none()
    if inv is None or not inv.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This invite link is invalid or has been disabled.")
    exp = inv.expires_at
    if exp is not None and (exp if exp.tzinfo else exp.replace(tzinfo=UTC)) < datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, "This invite link has expired.")
    if inv.uses >= inv.max_uses:
        raise HTTPException(status.HTTP_410_GONE, "This invite link has reached its usage limit.")
    t = await db.get(InterviewTemplate, inv.template_id)
    org = await db.get(Organization, inv.organization_id)
    if t is None or org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This invite link is no longer available.")
    return inv, t, org


@router.get("/{token}")
async def view_invite(token: str, db: DB) -> dict[str, Any]:
    inv, t, org = await _valid_invite(db, token)
    return {
        "organization": {"name": org.name, "kind": org.kind},
        "template": {
            "name": t.name,
            "role_title": ROLES[t.role_key].title if t.role_key in ROLES else t.role_key,
            "duration_minutes": t.duration_minutes,
            "interview_type": t.interview_type,
            "difficulty": t.difficulty,
            "rounds": [{"title": r.get("title"), "kind": r.get("kind"), "minutes": r.get("minutes")} for r in t.rounds],
        },
        "email_domain": inv.email_domain,
    }


@router.post("/{token}/accept")
async def accept_invite(token: str, request: Request, user: CurrentUser, db: DB) -> dict[str, Any]:
    inv, t, org = await _valid_invite(db, token)
    if inv.email_domain and not user.email.lower().endswith("@" + inv.email_domain):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"This invite requires an @{inv.email_domain} email address.")
    # identity: reuse an unfinished interview from this invite instead of creating duplicates
    existing = (
        await db.execute(
            select(Interview).where(Interview.invite_id == inv.id, Interview.candidate_id == user.id, Interview.status.in_(("planned", "in_progress")))
        )
    ).scalar_one_or_none()
    if existing:
        return interview_detail(existing)
    member = (
        await db.execute(select(OrganizationMember).where(OrganizationMember.organization_id == org.id, OrganizationMember.user_id == user.id))
    ).scalar_one_or_none()
    if member is None:
        db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role="candidate"))
    await enforce_limits(db, org_id=org.id, user=user)
    resume = (await db.execute(select(Resume).where(Resume.user_id == user.id).order_by(Resume.created_at.desc()).limit(1))).scalar_one_or_none()
    iv = await create_interview(
        db,
        user,
        role_key=t.role_key,
        interview_type=t.interview_type,
        duration_minutes=t.duration_minutes,
        difficulty=t.difficulty,
        resume=resume,
        template=t,
        organization_id=org.id,
        invite_id=inv.id,
        title=f"{t.name} — {org.name}",
    )
    inv.uses += 1
    audit(db, "invite.accept", user.id, org.id, "invite", str(inv.id), client_ip(request))
    await db.commit()
    return interview_detail(iv)
