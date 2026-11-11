"""Request dependencies: authentication, role checks and tenant resolution."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import Interview, Organization, OrganizationMember, User
from intervue_security import TokenError, decode_token, encode_token

SESSION_COOKIE = "iv_session"

DB = Annotated[AsyncSession, Depends(get_db)]


def issue_session(user: User) -> str:
    s = get_settings()
    return encode_token(s.auth_secret, str(user.id), "session", s.session_ttl_hours * 3600, {"role": user.role})


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


async def optional_user(request: Request, db: DB) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else None
    if not token:
        return None
    try:
        payload = decode_token(get_settings().auth_secret, token, "session")
        user = await db.get(User, uuid.UUID(payload["sub"]))
    except (TokenError, ValueError, KeyError):
        return None
    if user is None or not user.is_active:
        return None
    return user


async def current_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in to continue.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_roles(*roles: str):  # type: ignore[no-untyped-def]
    async def dep(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this area.")
        return user

    return dep


SuperAdmin = Annotated[User, Depends(require_roles("super_admin"))]


@dataclass
class OrgContext:
    org: Organization
    user: User
    member_role: str


async def org_context(
    user: CurrentUser,
    db: DB,
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
) -> OrgContext:
    """Resolve the organisation from the caller's *membership*. A client-supplied org id is only
    used to choose between orgs the caller already administers."""
    q = (
        select(OrganizationMember, Organization)
        .join(Organization, Organization.id == OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == user.id, OrganizationMember.role.in_(("admin", "reviewer")))
    )
    rows = (await db.execute(q)).all()
    if x_org_id:
        rows = [r for r in rows if str(r[1].id) == x_org_id]
    if not rows:
        if user.role == "super_admin" and x_org_id:
            org = await db.get(Organization, uuid.UUID(x_org_id))
            if org:
                return OrgContext(org=org, user=user, member_role="admin")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not an administrator of an organization.")
    member, org = rows[0]
    return OrgContext(org=org, user=user, member_role=member.role)


Org = Annotated[OrgContext, Depends(org_context)]


async def can_view_interview(db: AsyncSession, user: User, interview: Interview) -> bool:
    if interview.candidate_id == user.id or user.role == "super_admin":
        return True
    if interview.organization_id is None:
        return False
    m = (
        await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == interview.organization_id,
                OrganizationMember.user_id == user.id,
                OrganizationMember.role.in_(("admin", "reviewer")),
            )
        )
    ).scalar_one_or_none()
    return m is not None


async def load_interview(db: AsyncSession, interview_id: uuid.UUID, user: User, *, candidate_only: bool = False) -> Interview:
    interview = await db.get(Interview, interview_id)
    if interview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found.")
    if candidate_only:
        if interview.candidate_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found.")
    elif not await can_view_interview(db, user, interview):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found.")
    return interview
