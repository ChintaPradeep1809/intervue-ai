from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import DB, SESSION_COOKIE, CurrentUser, client_ip, issue_session
from app.models import CandidateProfile, OrganizationMember, User, utcnow
from app.services.audit import audit
from intervue_security import hash_password, needs_rehash, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


EMAIL_RE = r"^[^@\s]{1,64}@[^@\s]{1,255}\.[A-Za-z]{2,}$"


class RegisterIn(BaseModel):
    email: str = Field(pattern=EMAIL_RE, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    account_type: str = Field(default="candidate", pattern="^(candidate|organization)$")


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=128)


def user_out(u: User, orgs: list[dict[str, Any]] | None = None, onboarding_completed: bool | None = None) -> dict[str, Any]:
    return {
        "id": str(u.id),
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role,
        "is_demo": u.is_demo,
        "organizations": orgs or [],
        "onboarding_completed": onboarding_completed,
    }


async def user_payload(db: DB, u: User) -> dict[str, Any]:
    from app.models import Organization

    rows = (
        await db.execute(
            select(OrganizationMember, Organization)
            .join(Organization, Organization.id == OrganizationMember.organization_id)
            .where(OrganizationMember.user_id == u.id)
        )
    ).all()
    orgs = [{"id": str(o.id), "name": o.name, "role": m.role, "kind": o.kind} for m, o in rows]
    prof = (await db.execute(select(CandidateProfile).where(CandidateProfile.user_id == u.id))).scalar_one_or_none()
    return user_out(u, orgs, prof.onboarding_completed if prof else False)


def set_session_cookie(resp: Response, user: User) -> None:
    s = get_settings()
    resp.set_cookie(
        SESSION_COOKIE,
        issue_session(user),
        max_age=s.session_ttl_hours * 3600,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/register", status_code=201)
async def register(body: RegisterIn, request: Request, response: Response, db: DB) -> dict[str, Any]:
    email = body.email.lower().strip()
    exists = (await db.execute(select(User).where(func.lower(User.email) == email))).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name.strip(),
        role="organization_admin" if body.account_type == "organization" else "candidate",
        last_login_at=utcnow(),
    )
    db.add(user)
    await db.flush()
    db.add(CandidateProfile(user_id=user.id))
    audit(db, "user.register", user.id, ip=client_ip(request), account_type=body.account_type)
    await db.commit()
    set_session_cookie(response, user)
    return await user_payload(db, user)


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, db: DB) -> dict[str, Any]:
    user = (await db.execute(select(User).where(func.lower(User.email) == body.email.lower().strip()))).scalar_one_or_none()
    if user is None or not user.password_hash or not verify_password(user.password_hash, body.password):
        audit(db, "user.login_failed", None, ip=client_ip(request), email=body.email.lower()[:120])
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been disabled.")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    user.last_login_at = utcnow()
    audit(db, "user.login", user.id, ip=client_ip(request))
    await db.commit()
    set_session_cookie(response, user)
    return await user_payload(db, user)


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: CurrentUser, db: DB) -> dict[str, Any]:
    return await user_payload(db, user)


# ----------------------------------------------------------------------------- Google OAuth
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"


def _redirect_uri() -> str:
    return f"{get_settings().public_web_url}/api/auth/google/callback"


@router.get("/google/start")
async def google_start() -> RedirectResponse:
    s = get_settings()
    if not s.google_client_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Google sign-in is not configured.")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": s.google_client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    resp = RedirectResponse(f"{GOOGLE_AUTH}?{urlencode(params)}")
    resp.set_cookie("iv_oauth_state", state, max_age=600, httponly=True, secure=s.cookie_secure, samesite="lax")
    return resp


@router.get("/google/callback")
async def google_callback(request: Request, db: DB, code: str = "", state: str = "") -> RedirectResponse:
    s = get_settings()
    if not s.google_client_id or not code or state != request.cookies.get("iv_oauth_state"):
        return RedirectResponse(f"{s.public_web_url}/auth/login?error=oauth")
    async with httpx.AsyncClient(timeout=10) as client:
        tok = await client.post(
            GOOGLE_TOKEN,
            data={
                "code": code,
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
                "redirect_uri": _redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
        if tok.status_code != 200:
            return RedirectResponse(f"{s.public_web_url}/auth/login?error=oauth")
        info = (await client.get(GOOGLE_USERINFO, headers={"Authorization": f"Bearer {tok.json()['access_token']}"})).json()
    if not info.get("email_verified"):
        return RedirectResponse(f"{s.public_web_url}/auth/login?error=unverified")
    user = (await db.execute(select(User).where((User.google_sub == info["sub"]) | (func.lower(User.email) == info["email"].lower())))).scalar_one_or_none()
    if user is None:
        user = User(email=info["email"].lower(), full_name=info.get("name", ""), google_sub=info["sub"])
        db.add(user)
        await db.flush()
        db.add(CandidateProfile(user_id=user.id))
    else:
        user.google_sub = user.google_sub or info["sub"]
    user.last_login_at = utcnow()
    audit(db, "user.login_google", user.id, ip=client_ip(request))
    await db.commit()
    resp = RedirectResponse(f"{s.public_web_url}/dashboard")
    set_session_cookie(resp, user)
    resp.delete_cookie("iv_oauth_state")
    return resp
