from __future__ import annotations

import csv
import io
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, func, or_, select

from app.config import get_settings
from app.deps import DB, CurrentUser, Org, client_ip
from app.models import (
    CandidateProfile,
    Evaluation,
    Interview,
    InterviewTemplate,
    Invite,
    KnowledgeDocument,
    Organization,
    OrganizationMember,
    Plan,
    Report,
    Resume,
    Subscription,
    User,
)
from app.services import rag
from app.services.audit import audit
from app.services.documents import ExtractionError, extract_text
from app.services.usage import flush, usage_scope
from intervue_engine import INTERVIEW_TYPES, ROLES, TOPICS, topic_label
from intervue_security import FileValidationError, validate_upload
from intervue_security.files import DOCUMENT_TYPES

router = APIRouter(prefix="/api", tags=["organization"])

ROUND_KINDS = {"introduction", "technical", "coding", "sql", "system_design", "behavioral"}


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or "org"
    return f"{s}-{secrets.token_hex(3)}"


class OrgCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    kind: str = Field(default="college", pattern="^(college|university|institute|bootcamp|company|other)$")


@router.post("/organizations", status_code=201)
async def create_org(body: OrgCreateIn, request: Request, user: CurrentUser, db: DB) -> dict[str, Any]:
    existing = (
        await db.execute(select(OrganizationMember).where(OrganizationMember.user_id == user.id, OrganizationMember.role == "admin"))
    ).scalar_one_or_none()
    if existing and user.role != "super_admin":
        raise HTTPException(status.HTTP_409_CONFLICT, "You already administer an organization.")
    org = Organization(
        name=body.name.strip(), slug=_slug(body.name), kind=body.kind, settings={"pass_threshold": 60, "retention_days": get_settings().data_retention_days}
    )
    db.add(org)
    await db.flush()
    db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role="admin"))
    if user.role == "candidate":
        user.role = "organization_admin"
    plan = (await db.execute(select(Plan).where(Plan.key == "college"))).scalar_one_or_none()
    if plan:
        db.add(Subscription(plan_id=plan.id, organization_id=org.id, status="trial", current_period_end=datetime.now(UTC) + timedelta(days=30)))
    audit(db, "org.create", user.id, org.id, "organization", str(org.id), client_ip(request))
    await db.commit()
    return {"id": str(org.id), "name": org.name, "slug": org.slug, "kind": org.kind}


def _pass(org: Organization) -> int:
    return int((org.settings or {}).get("pass_threshold", 60))


@router.get("/organization")
async def dashboard(ctx: Org, db: DB) -> dict[str, Any]:
    org = ctx.org
    base = select(Interview).where(Interview.organization_id == org.id)
    ivs = (await db.execute(base)).scalars().all()
    completed = [i for i in ivs if i.status == "completed" and i.overall_score is not None]
    started = [i for i in ivs if i.status in ("in_progress", "evaluating", "completed", "abandoned")]
    scores = [i.overall_score for i in completed if i.overall_score is not None]
    candidates = {i.candidate_id for i in ivs}
    member_candidates = (
        await db.execute(
            select(func.count()).select_from(OrganizationMember).where(OrganizationMember.organization_id == org.id, OrganizationMember.role == "candidate")
        )
    ).scalar_one()
    topic_rows = (
        await db.execute(
            select(Evaluation.topic, func.avg(Evaluation.score), func.count(Evaluation.id))
            .join(Interview, Interview.id == Evaluation.interview_id)
            .where(Interview.organization_id == org.id, Evaluation.topic != "introduction")
            .group_by(Evaluation.topic)
        )
    ).all()
    topics = sorted(
        ({"topic": t, "label": topic_label(t), "avg_score": round(float(a)), "answers": int(n)} for t, a, n in topic_rows), key=lambda x: -x["avg_score"]
    )
    tech = []
    for r in (await db.execute(select(Report).join(Interview).where(Interview.organization_id == org.id))).scalars():
        for s in r.data.get("section_scores", []):
            if s["category"] == "technical":
                tech.append(s["score"])
    buckets = [0] * 5
    for sc in scores:
        buckets[min(4, sc // 20)] += 1
    today = datetime.now(UTC).date()
    per_day = {(today - timedelta(days=d)).isoformat(): 0 for d in range(13, -1, -1)}
    for i in completed:
        if i.completed_at:
            k = i.completed_at.date().isoformat()
            if k in per_day:
                per_day[k] += 1
    recent = sorted(completed, key=lambda i: i.completed_at or i.created_at, reverse=True)[:6]
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_([i.candidate_id for i in recent])))).scalars()} if recent else {}
    return {
        "organization": {"id": str(org.id), "name": org.name, "kind": org.kind, "slug": org.slug, "settings": org.settings},
        "member_role": ctx.member_role,
        "stats": {
            "total_candidates": max(len(candidates), int(member_candidates)),
            "interviews_total": len(ivs),
            "interviews_completed": len(completed),
            "average_score": round(sum(scores) / len(scores)) if scores else None,
            "pass_rate": round(100 * sum(1 for s in scores if s >= _pass(org)) / len(scores)) if scores else None,
            "average_technical_score": round(sum(tech) / len(tech)) if tech else None,
            "completion_rate": round(100 * len(completed) / len(started)) if started else None,
            "pass_threshold": _pass(org),
        },
        "top_skills": topics[:5],
        "weakest_skills": list(reversed(topics[-5:])) if topics else [],
        "score_distribution": [{"range": f"{i * 20}-{i * 20 + 19 if i < 4 else 100}", "count": c} for i, c in enumerate(buckets)],
        "completions_by_day": [{"date": d, "count": c} for d, c in per_day.items()],
        "recent": [
            {
                "interview_id": str(i.id),
                "candidate": users[i.candidate_id].full_name if i.candidate_id in users else "",
                "role": i.plan.get("role_title"),
                "score": i.overall_score,
                "completed_at": i.completed_at,
            }
            for i in recent
        ],
    }


def _row(iv: Interview, u: User | None) -> dict[str, Any]:
    return {
        "interview_id": str(iv.id),
        "candidate_id": str(iv.candidate_id),
        "candidate_name": u.full_name if u else "",
        "candidate_email": u.email if u else "",
        "role": iv.plan.get("role_title", iv.role_key),
        "role_key": iv.role_key,
        "interview": iv.title,
        "score": iv.overall_score,
        "status": iv.status,
        "review_status": iv.review_status,
        "date": iv.completed_at or iv.created_at,
    }


@router.get("/organization/candidates")
async def candidates(
    ctx: Org,
    db: DB,
    q: str = "",
    role: str = "",
    status_: str = Query("", alias="status"),
    review: str = "",
    min_score: int | None = None,
    max_score: int | None = None,
    sort: str = "date",
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    stmt = select(Interview, User).join(User, User.id == Interview.candidate_id).where(Interview.organization_id == ctx.org.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like)))
    if role:
        stmt = stmt.where(Interview.role_key == role)
    if status_:
        stmt = stmt.where(Interview.status == status_)
    if review:
        stmt = stmt.where(Interview.review_status == review)
    if min_score is not None:
        stmt = stmt.where(Interview.overall_score >= min_score)
    if max_score is not None:
        stmt = stmt.where(Interview.overall_score <= max_score)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    order = {"score": Interview.overall_score.desc().nulls_last(), "name": User.full_name.asc()}.get(sort, Interview.created_at.desc())
    page_size = max(1, min(page_size, 100))
    rows = (await db.execute(stmt.order_by(order).limit(page_size).offset((max(1, page) - 1) * page_size))).all()
    return {"items": [_row(iv, u) for iv, u in rows], "total": int(total), "page": page, "page_size": page_size}


@router.get("/organization/candidates/{candidate_id}")
async def candidate_detail(candidate_id: uuid.UUID, ctx: Org, db: DB) -> dict[str, Any]:
    ivs = (
        (
            await db.execute(
                select(Interview).where(Interview.organization_id == ctx.org.id, Interview.candidate_id == candidate_id).order_by(Interview.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    is_member = (
        await db.execute(select(OrganizationMember).where(OrganizationMember.organization_id == ctx.org.id, OrganizationMember.user_id == candidate_id))
    ).scalar_one_or_none()
    if not ivs and not is_member:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found.")
    u = await db.get(User, candidate_id)
    prof = (await db.execute(select(CandidateProfile).where(CandidateProfile.user_id == candidate_id))).scalar_one_or_none()
    resume_ids = {i.resume_id for i in ivs if i.resume_id}
    resumes = (await db.execute(select(Resume).where(Resume.id.in_(resume_ids)))).scalars().all() if resume_ids else []
    reports = {r.interview_id: r for r in (await db.execute(select(Report).where(Report.interview_id.in_([i.id for i in ivs])))).scalars()} if ivs else {}
    latest = next((reports[i.id] for i in ivs if i.id in reports), None)
    return {
        "candidate": {
            "id": str(candidate_id),
            "full_name": u.full_name if u else "",
            "email": u.email if u else "",
            "experience_years": prof.experience_years if prof else None,
            "headline": prof.headline if prof else "",
        },
        "resumes": [{"id": str(r.id), "filename": r.filename} for r in resumes],
        "interviews": [{**_row(i, u), "analysis_skills": [s["name"] for s in i.analysis.get("skills", [])]} for i in ivs],
        "latest_report": latest.data if latest else None,
    }


class ReviewIn(BaseModel):
    review_status: str = Field(pattern="^(pending|shortlisted|on_hold|rejected)$")
    notes: str = Field(default="", max_length=5000)


@router.patch("/organization/interviews/{interview_id}/review")
async def review(interview_id: uuid.UUID, body: ReviewIn, request: Request, ctx: Org, db: DB) -> dict[str, Any]:
    iv = await db.get(Interview, interview_id)
    if iv is None or iv.organization_id != ctx.org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found.")
    iv.review_status, iv.reviewer_notes = body.review_status, body.notes
    audit(db, "interview.review", ctx.user.id, ctx.org.id, "interview", str(iv.id), client_ip(request), review_status=body.review_status)
    await db.commit()
    return {"ok": True, "review_status": iv.review_status}


@router.get("/organization/compare")
async def compare(ctx: Org, db: DB, ids: str) -> dict[str, Any]:
    id_list = [uuid.UUID(x) for x in ids.split(",") if x.strip()][:4]
    rows = (
        await db.execute(
            select(Interview, User, Report)
            .join(User, User.id == Interview.candidate_id)
            .join(Report, Report.interview_id == Interview.id)
            .where(Interview.organization_id == ctx.org.id, Interview.id.in_(id_list))
        )
    ).all()
    return {
        "items": [
            {
                **_row(iv, u),
                "section_scores": rep.data.get("section_scores", []),
                "category_scores": rep.data.get("category_scores", []),
                "topic_scores": rep.data.get("topic_scores", []),
                "strong_areas": rep.data.get("strong_areas", []),
                "weak_areas": rep.data.get("weak_areas", []),
                "readiness": rep.data.get("readiness_label"),
            }
            for iv, u, rep in rows
        ]
    }


@router.get("/organization/export.csv")
async def export_csv(request: Request, ctx: Org, db: DB) -> StreamingResponse:
    rows = (
        await db.execute(
            select(Interview, User, Report)
            .join(User, User.id == Interview.candidate_id)
            .outerjoin(Report, Report.interview_id == Interview.id)
            .where(Interview.organization_id == ctx.org.id)
            .order_by(Interview.created_at.desc())
        )
    ).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "candidate_name",
            "email",
            "role",
            "interview",
            "status",
            "overall_score",
            "readiness",
            "technical",
            "communication",
            "problem_solving",
            "coding",
            "system_design",
            "strong_areas",
            "weak_areas",
            "review_status",
            "completed_at",
        ]
    )
    for iv, u, rep in rows:
        sec = {s["category"]: s["score"] for s in (rep.data.get("section_scores", []) if rep else [])}

        def safe(v: Any) -> Any:
            s = "" if v is None else str(v)
            return "'" + s if s[:1] in ("=", "+", "-", "@") else s  # CSV injection guard

        w.writerow(
            [
                safe(u.full_name),
                safe(u.email),
                safe(iv.plan.get("role_title")),
                safe(iv.title),
                iv.status,
                iv.overall_score or "",
                safe(rep.data.get("readiness_label") if rep else ""),
                sec.get("technical", ""),
                sec.get("communication", ""),
                sec.get("problem_solving", ""),
                sec.get("coding", ""),
                sec.get("system_design", ""),
                safe("; ".join(rep.data.get("strong_areas", [])) if rep else ""),
                safe("; ".join(rep.data.get("weak_areas", [])) if rep else ""),
                iv.review_status,
                iv.completed_at.isoformat() if iv.completed_at else "",
            ]
        )
    audit(db, "org.export", ctx.user.id, ctx.org.id, ip=client_ip(request), rows=len(rows))
    await db.commit()
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{ctx.org.slug}-results.csv"'}
    )


# ----------------------------------------------------------------------------- templates
class RoundIn(BaseModel):
    kind: str
    title: str = Field(default="", max_length=120)
    minutes: int = Field(ge=1, le=60)
    topics: list[str] = []
    question_count: int | None = Field(default=None, ge=1, le=12)
    language: str | None = None


class TemplateIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    role_key: str
    experience_level: str = Field(default="junior", pattern="^(entry|junior|mid|senior|lead)$")
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    interview_type: str = "full"
    rounds: list[RoundIn] = []
    scoring_weights: dict[str, float] = {}
    jd_text: str = Field(default="", max_length=30000)
    is_active: bool = True


def _validate_template(body: TemplateIn) -> None:
    if body.role_key not in ROLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown role.")
    if body.interview_type not in INTERVIEW_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown interview type.")
    for r in body.rounds:
        if r.kind not in ROUND_KINDS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown round kind '{r.kind}'.")
        bad = [t for t in r.topics if t not in TOPICS]
        if bad:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown topics: {', '.join(bad)}")
        if r.kind == "technical" and not r.topics:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Technical rounds need at least one topic.")
    if sum(r.minutes for r in body.rounds) > 120:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Total duration must be 120 minutes or less.")


def template_out(t: InterviewTemplate, invites: list[Invite] | None = None) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "name": t.name,
        "role_key": t.role_key,
        "role_title": ROLES[t.role_key].title if t.role_key in ROLES else t.role_key,
        "experience_level": t.experience_level,
        "duration_minutes": t.duration_minutes,
        "difficulty": t.difficulty,
        "interview_type": t.interview_type,
        "rounds": t.rounds,
        "scoring_weights": t.scoring_weights,
        "jd_text": t.jd_text,
        "is_active": t.is_active,
        "is_global": t.organization_id is None,
        "created_at": t.created_at,
        "invites": [invite_out(i) for i in (invites or [])],
    }


def invite_out(i: Invite) -> dict[str, Any]:
    return {
        "id": str(i.id),
        "token": i.token,
        "label": i.label,
        "url": f"{get_settings().public_web_url}/invite/{i.token}",
        "uses": i.uses,
        "max_uses": i.max_uses,
        "expires_at": i.expires_at,
        "is_active": i.is_active,
        "email_domain": i.email_domain,
    }


def _apply_template(t: InterviewTemplate, body: TemplateIn) -> None:
    t.name, t.role_key, t.experience_level, t.difficulty = body.name.strip(), body.role_key, body.experience_level, body.difficulty
    t.interview_type, t.scoring_weights, t.jd_text, t.is_active = body.interview_type, body.scoring_weights, body.jd_text, body.is_active
    t.rounds = [{**r.model_dump(), "title": r.title or r.kind.replace("_", " ").title()} for r in body.rounds]
    t.topics = sorted({tp for r in body.rounds for tp in r.topics})
    t.duration_minutes = sum(r.minutes for r in body.rounds) or 45


@router.get("/organization/templates")
async def list_templates(ctx: Org, db: DB) -> dict[str, Any]:
    ts = (
        (
            await db.execute(
                select(InterviewTemplate)
                .where(or_(InterviewTemplate.organization_id == ctx.org.id, InterviewTemplate.organization_id.is_(None)))
                .order_by(InterviewTemplate.organization_id.is_(None), InterviewTemplate.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    invites = (await db.execute(select(Invite).where(Invite.organization_id == ctx.org.id).order_by(Invite.created_at.desc()))).scalars().all()
    return {"items": [template_out(t, [i for i in invites if i.template_id == t.id]) for t in ts]}


@router.post("/organization/templates", status_code=201)
async def create_template(body: TemplateIn, request: Request, ctx: Org, db: DB) -> dict[str, Any]:
    _validate_template(body)
    t = InterviewTemplate(organization_id=ctx.org.id, created_by=ctx.user.id, name=body.name)
    _apply_template(t, body)
    db.add(t)
    audit(db, "template.create", ctx.user.id, ctx.org.id, "template", "", client_ip(request), name=body.name)
    await db.commit()
    return template_out(t)


async def _own_template(db: DB, ctx: Org, template_id: uuid.UUID, *, allow_global: bool = False) -> InterviewTemplate:
    t = await db.get(InterviewTemplate, template_id)
    if t is None or (t.organization_id != ctx.org.id and not (allow_global and t.organization_id is None)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found.")
    return t


@router.put("/organization/templates/{template_id}")
async def update_template(template_id: uuid.UUID, body: TemplateIn, ctx: Org, db: DB) -> dict[str, Any]:
    _validate_template(body)
    t = await _own_template(db, ctx, template_id)
    _apply_template(t, body)
    await db.commit()
    return template_out(t)


@router.delete("/organization/templates/{template_id}")
async def delete_template(template_id: uuid.UUID, ctx: Org, db: DB) -> dict[str, bool]:
    t = await _own_template(db, ctx, template_id)
    await db.delete(t)
    await db.commit()
    return {"ok": True}


class InviteIn(BaseModel):
    label: str = Field(default="", max_length=200)
    max_uses: int = Field(default=100, ge=1, le=10000)
    expires_in_days: int = Field(default=30, ge=1, le=365)
    email_domain: str | None = Field(default=None, max_length=120)


@router.post("/organization/templates/{template_id}/invites", status_code=201)
async def create_invite(template_id: uuid.UUID, body: InviteIn, request: Request, ctx: Org, db: DB) -> dict[str, Any]:
    t = await _own_template(db, ctx, template_id, allow_global=True)
    inv = Invite(
        organization_id=ctx.org.id,
        template_id=t.id,
        token=secrets.token_urlsafe(18),
        label=body.label or t.name,
        max_uses=body.max_uses,
        expires_at=datetime.now(UTC) + timedelta(days=body.expires_in_days),
        email_domain=(body.email_domain or "").lower().lstrip("@") or None,
        created_by=ctx.user.id,
    )
    db.add(inv)
    audit(db, "invite.create", ctx.user.id, ctx.org.id, "invite", "", client_ip(request), template=str(t.id))
    await db.commit()
    return invite_out(inv)


@router.patch("/organization/invites/{invite_id}")
async def toggle_invite(invite_id: uuid.UUID, ctx: Org, db: DB, active: bool = True) -> dict[str, Any]:
    inv = await db.get(Invite, invite_id)
    if inv is None or inv.organization_id != ctx.org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found.")
    inv.is_active = active
    await db.commit()
    return invite_out(inv)


# ----------------------------------------------------------------------------- reports / analytics
@router.get("/organization/reports")
async def org_reports(ctx: Org, db: DB, role: str = "") -> dict[str, Any]:
    stmt = select(Report, Interview).join(Interview).where(Interview.organization_id == ctx.org.id)
    if role:
        stmt = stmt.where(Interview.role_key == role)
    rows = (await db.execute(stmt)).all()
    cat: dict[str, list[int]] = {}
    sec: dict[str, list[int]] = {}
    readiness: dict[str, int] = {}
    rec: dict[str, int] = {}
    by_role: dict[str, list[int]] = {}
    for rep, iv in rows:
        for c in rep.data.get("category_scores", []):
            cat.setdefault(c["category"], []).append(c["score"])
        for s in rep.data.get("section_scores", []):
            sec.setdefault(s["category"], []).append(s["score"])
        readiness[rep.data.get("readiness_label", "")] = readiness.get(rep.data.get("readiness_label", ""), 0) + 1
        for t in rep.data.get("recommended_topics", []):
            rec[t] = rec.get(t, 0) + 1
        by_role.setdefault(iv.plan.get("role_title", iv.role_key), []).append(rep.overall_score)
    avg = lambda v: round(sum(v) / len(v)) if v else None  # noqa: E731
    return {
        "reports": len(rows),
        "category_averages": [{"category": k, "score": avg(v)} for k, v in cat.items()],
        "section_averages": [{"category": k, "score": avg(v)} for k, v in sec.items()],
        "readiness": [{"label": k, "count": v} for k, v in readiness.items() if k],
        "common_gaps": [{"concept": k, "count": v} for k, v in sorted(rec.items(), key=lambda kv: -kv[1])[:10]],
        "by_role": [{"role": k, "average": avg(v), "count": len(v)} for k, v in by_role.items()],
    }


# ----------------------------------------------------------------------------- settings & deletion
class OrgSettingsIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    kind: str = Field(pattern="^(college|university|institute|bootcamp|company|other)$")
    pass_threshold: int = Field(ge=0, le=100)
    retention_days: int = Field(ge=7, le=3650)


@router.put("/organization/settings")
async def update_settings(body: OrgSettingsIn, request: Request, ctx: Org, db: DB) -> dict[str, Any]:
    if ctx.member_role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can change settings.")
    org = ctx.org
    org.name, org.kind = body.name.strip(), body.kind
    org.settings = {**(org.settings or {}), "pass_threshold": body.pass_threshold, "retention_days": body.retention_days}
    audit(db, "org.settings", ctx.user.id, org.id, ip=client_ip(request), **body.model_dump())
    await db.commit()
    return {"ok": True, "settings": org.settings, "name": org.name, "kind": org.kind}


class DeleteOrgIn(BaseModel):
    confirm_name: str


@router.post("/organization/delete")
async def delete_org(body: DeleteOrgIn, request: Request, ctx: Org, db: DB) -> dict[str, bool]:
    if ctx.member_role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can delete the organization.")
    if body.confirm_name.strip() != ctx.org.name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Type the organization name exactly to confirm.")
    audit(db, "org.delete", ctx.user.id, None, "organization", str(ctx.org.id), client_ip(request), name=ctx.org.name)
    await db.execute(delete(Interview).where(Interview.organization_id == ctx.org.id))
    await db.delete(ctx.org)
    if ctx.user.role == "organization_admin":
        ctx.user.role = "candidate"
    await db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------- knowledge base
@router.get("/organization/knowledge")
async def list_knowledge(ctx: Org, db: DB) -> dict[str, Any]:
    docs = (
        (await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.organization_id == ctx.org.id).order_by(KnowledgeDocument.created_at.desc())))
        .scalars()
        .all()
    )
    return {
        "items": [
            {"id": str(d.id), "title": d.title, "kind": d.kind, "filename": d.filename, "chunks": d.chunk_count, "created_at": d.created_at} for d in docs
        ]
    }


@router.post("/organization/knowledge", status_code=201)
async def add_knowledge(
    ctx: Org,
    db: DB,
    title: str = Form(..., min_length=2, max_length=200),
    kind: str = Form("guidelines", pattern="^(guidelines|question_bank|topics|role_description)$"),
    text: str = Form("", max_length=200_000),
    file: UploadFile | None = File(None),
) -> dict[str, Any]:
    filename = ""
    if file is not None:
        data = await file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
        try:
            v = validate_upload(file.filename or "", data, DOCUMENT_TYPES, get_settings().max_upload_mb * 1024 * 1024)
            text = extract_text(data, v.mime_type)
            filename = v.filename
        except (FileValidationError, ExtractionError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if len(text.strip()) < 20:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide document text or a file.")
    with usage_scope(ctx.user.id, ctx.org.id, None) as scope:
        doc = await rag.ingest(db, ctx.org.id, title, kind, filename, text)
        flush(db, scope)
    await db.commit()
    return {"id": str(doc.id), "title": doc.title, "chunks": doc.chunk_count}


@router.delete("/organization/knowledge/{doc_id}")
async def delete_knowledge(doc_id: uuid.UUID, ctx: Org, db: DB) -> dict[str, bool]:
    d = await db.get(KnowledgeDocument, doc_id)
    if d is None or d.organization_id != ctx.org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    await db.delete(d)
    await db.commit()
    return {"ok": True}


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)


@router.post("/organization/knowledge/search")
async def search_knowledge(body: SearchIn, ctx: Org, db: DB) -> dict[str, Any]:
    with usage_scope(ctx.user.id, ctx.org.id, None) as scope:
        hits = await rag.retrieve(db, ctx.org.id, body.query, k=5)
        flush(db, scope)
    await db.commit()
    return {"items": [{"score": round(s, 3), "content": c.content[:800], "document_id": str(c.document_id)} for s, c in hits]}


__all__ = ["and_", "router"]
