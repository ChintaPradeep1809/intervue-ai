"""Super-admin: command center, users, organisations, usage & cost, question bank, plans, pricing."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text

from app.config import get_settings
from app.deps import DB, SuperAdmin, client_ip
from app.models import (
    AppSetting,
    AuditLog,
    CostRecord,
    Interview,
    Organization,
    OrganizationLimit,
    OrganizationMember,
    Plan,
    Question,
    Subscription,
    UsageRecord,
    User,
)
from app.services import orchestrator
from app.services.ai import provider_summary
from app.services.audit import audit
from app.services.coding import worker_client
from app.services.metrics import metrics
from app.services.storage import get_storage
from app.services.usage import fx_rate, load_fx_override, load_pricing_overrides, pricing
from intervue_ai import PricingConfig
from intervue_engine import TOPICS

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/command-center")
async def command_center(_: SuperAdmin, db: DB) -> dict[str, Any]:
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "down"
    try:
        worker = await worker_client().health()
        worker_status = {"status": "ok", **worker}
    except Exception as exc:
        worker_status = {"status": "down", "error": str(exc)[:200]}
    since = datetime.now(UTC) - timedelta(days=30)
    usage = (
        await db.execute(
            select(
                UsageRecord.kind,
                func.sum(UsageRecord.input_tokens),
                func.sum(UsageRecord.output_tokens),
                func.sum(UsageRecord.quantity),
                func.sum(UsageRecord.cost_usd),
                func.count(UsageRecord.id),
            )
            .where(UsageRecord.created_at >= since)
            .group_by(UsageRecord.kind)
        )
    ).all()
    by_kind = {
        k: {"input_tokens": int(i or 0), "output_tokens": int(o or 0), "quantity": float(q or 0), "cost_usd": round(float(c or 0), 4), "events": int(n)}
        for k, i, o, q, c, n in usage
    }
    counts = dict((await db.execute(select(Interview.status, func.count(Interview.id)).group_by(Interview.status))).all())
    total_cost = sum(v["cost_usd"] for v in by_kind.values())
    completed_30d = (await db.execute(select(func.count(Interview.id)).where(Interview.status == "completed", Interview.completed_at >= since))).scalar_one()
    return {
        "providers": provider_summary(),
        "database": db_status,
        "storage": "ok" if await get_storage().healthy() else "down",
        "worker": worker_status,
        "usage_30d": by_kind,
        "ai_tokens_30d": sum(v["input_tokens"] + v["output_tokens"] for k, v in by_kind.items() if k == "llm"),
        "voice_minutes_30d": round(by_kind.get("voice", {}).get("quantity", 0) / 60, 1),
        "estimated_cost_usd_30d": round(total_cost, 4),
        "estimated_cost_inr_30d": round(total_cost * fx_rate(), 2),
        "avg_cost_per_interview_usd": round(total_cost / completed_30d, 4) if completed_30d else None,
        "active_interviews": {"connected": orchestrator.hub.active_interviews(), "in_progress": int(counts.get("in_progress", 0))},
        "interviews_by_status": {k: int(v) for k, v in counts.items()},
        "metrics": metrics.snapshot(),
        "fx_rate_usd_inr": fx_rate(),
    }


@router.get("/users")
async def users(_: SuperAdmin, db: DB, q: str = "", role: str = "", page: int = 1) -> dict[str, Any]:
    stmt = select(User).where(User.is_demo.is_(False))
    if q:
        stmt = stmt.where(or_(func.lower(User.email).like(f"%{q.lower()}%"), func.lower(User.full_name).like(f"%{q.lower()}%")))
    if role:
        stmt = stmt.where(User.role == role)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(User.created_at.desc()).limit(50).offset((max(1, page) - 1) * 50))).scalars().all()
    ic = (
        dict(
            (
                await db.execute(
                    select(Interview.candidate_id, func.count(Interview.id))
                    .where(Interview.candidate_id.in_([u.id for u in rows]))
                    .group_by(Interview.candidate_id)
                )
            ).all()
        )
        if rows
        else {}
    )
    return {
        "total": int(total),
        "items": [
            {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "is_active": u.is_active,
                "created_at": u.created_at,
                "last_login_at": u.last_login_at,
                "interviews": int(ic.get(u.id, 0)),
            }
            for u in rows
        ],
    }


class UserPatch(BaseModel):
    role: str | None = Field(default=None, pattern="^(candidate|organization_admin|super_admin)$")
    is_active: bool | None = None


@router.patch("/users/{user_id}")
async def patch_user(user_id: uuid.UUID, body: UserPatch, request: Request, admin: SuperAdmin, db: DB) -> dict[str, Any]:
    u = await db.get(User, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    if u.id == admin.id and (body.role not in (None, "super_admin") or body.is_active is False):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't demote or disable yourself.")
    if body.role:
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    audit(db, "admin.user_update", admin.id, target_type="user", target_id=str(u.id), ip=client_ip(request), **body.model_dump(exclude_none=True))
    await db.commit()
    return {"ok": True}


@router.get("/organizations")
async def organizations(_: SuperAdmin, db: DB) -> dict[str, Any]:
    orgs = (await db.execute(select(Organization).order_by(Organization.created_at.desc()))).scalars().all()
    ivc = dict(
        (
            await db.execute(
                select(Interview.organization_id, func.count(Interview.id)).where(Interview.organization_id.is_not(None)).group_by(Interview.organization_id)
            )
        ).all()
    )
    mem = dict(
        (await db.execute(select(OrganizationMember.organization_id, func.count(OrganizationMember.id)).group_by(OrganizationMember.organization_id))).all()
    )
    cost = dict(
        (
            await db.execute(
                select(UsageRecord.organization_id, func.sum(UsageRecord.cost_usd))
                .where(UsageRecord.organization_id.is_not(None))
                .group_by(UsageRecord.organization_id)
            )
        ).all()
    )
    subs = {
        s.organization_id: (s, p) for s, p in (await db.execute(select(Subscription, Plan).join(Plan).where(Subscription.organization_id.is_not(None)))).all()
    }
    limits = {lim.organization_id: lim for lim in (await db.execute(select(OrganizationLimit))).scalars()}
    out = []
    for o in orgs:
        sp = subs.get(o.id)
        lim = limits.get(o.id)
        out.append(
            {
                "id": str(o.id),
                "name": o.name,
                "kind": o.kind,
                "created_at": o.created_at,
                "interviews": int(ivc.get(o.id, 0)),
                "members": int(mem.get(o.id, 0)),
                "cost_usd": round(float(cost.get(o.id) or 0), 4),
                "plan": sp[1].key if sp else None,
                "subscription_status": sp[0].status if sp else None,
                "limits": {
                    "interviews_per_month": lim.interviews_per_month,
                    "voice_minutes_per_month": lim.voice_minutes_per_month,
                    "ai_tokens_per_month": lim.ai_tokens_per_month,
                    "seats": lim.seats,
                }
                if lim
                else None,
            }
        )
    return {"items": out}


class OrgAdminPatch(BaseModel):
    plan_key: str | None = None
    interviews_per_month: int | None = Field(default=None, ge=0)
    voice_minutes_per_month: int | None = Field(default=None, ge=0)
    ai_tokens_per_month: int | None = Field(default=None, ge=0)
    seats: int | None = Field(default=None, ge=0)


@router.patch("/organizations/{org_id}")
async def patch_org(org_id: uuid.UUID, body: OrgAdminPatch, request: Request, admin: SuperAdmin, db: DB) -> dict[str, Any]:
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found.")
    if body.plan_key:
        plan = (await db.execute(select(Plan).where(Plan.key == body.plan_key))).scalar_one_or_none()
        if plan is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown plan.")
        sub = (await db.execute(select(Subscription).where(Subscription.organization_id == org.id))).scalar_one_or_none()
        if sub is None:
            db.add(Subscription(plan_id=plan.id, organization_id=org.id, status="active"))
        else:
            sub.plan_id, sub.status = plan.id, "active"
    lim_fields = body.model_dump(exclude={"plan_key"}, exclude_unset=True)
    if lim_fields:
        lim = (await db.execute(select(OrganizationLimit).where(OrganizationLimit.organization_id == org.id))).scalar_one_or_none()
        if lim is None:
            lim = OrganizationLimit(organization_id=org.id)
            db.add(lim)
        for k, v in lim_fields.items():
            setattr(lim, k, v)
    audit(db, "admin.org_update", admin.id, org.id, ip=client_ip(request), **body.model_dump(exclude_none=True))
    await db.commit()
    return {"ok": True}


@router.get("/usage")
async def usage(_: SuperAdmin, db: DB, days: int = 30) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))
    recs = (await db.execute(select(UsageRecord).where(UsageRecord.created_at >= since))).scalars().all()
    daily: dict[str, dict[str, float]] = {}
    by_task: dict[str, dict[str, float]] = {}
    for r in recs:
        d = r.created_at.date().isoformat()
        daily.setdefault(d, {"cost_usd": 0.0, "llm_tokens": 0.0, "voice_seconds": 0.0})
        daily[d]["cost_usd"] += r.cost_usd
        if r.kind == "llm":
            daily[d]["llm_tokens"] += r.input_tokens + r.output_tokens
            t = by_task.setdefault(r.task, {"calls": 0, "tokens": 0, "cost_usd": 0.0, "latency_ms_total": 0, "fallbacks": 0})
            t["calls"] += 1
            t["tokens"] += r.input_tokens + r.output_tokens
            t["cost_usd"] += r.cost_usd
            t["latency_ms_total"] += r.latency_ms
            t["fallbacks"] += int(r.fallback_used)
        if r.kind == "voice":
            daily[d]["voice_seconds"] += r.quantity
    costs = (await db.execute(select(CostRecord, Interview).join(Interview).order_by(CostRecord.updated_at.desc()).limit(50))).all()
    plans = {p.key: p for p in (await db.execute(select(Plan))).scalars()}
    all_costs = [c.estimated_cost_usd for c, _ in costs]
    avg_cost = sum(all_costs) / len(all_costs) if all_costs else 0.0
    margins = []
    for p in plans.values():
        n = p.limits.get("interviews_per_month")
        if p.price_monthly_usd and n:
            cost = avg_cost * n
            margins.append(
                {
                    "plan": p.name,
                    "price_usd": p.price_monthly_usd,
                    "interviews": n,
                    "est_cost_at_limit_usd": round(cost, 2),
                    "gross_margin_pct": round(100 * (p.price_monthly_usd - cost) / p.price_monthly_usd, 1),
                }
            )
    return {
        "daily": [{"date": d, **{k: round(v, 4) for k, v in vals.items()}} for d, vals in sorted(daily.items())],
        "by_task": [
            {
                "task": k,
                "calls": int(v["calls"]),
                "tokens": int(v["tokens"]),
                "cost_usd": round(v["cost_usd"], 4),
                "avg_latency_ms": round(v["latency_ms_total"] / v["calls"]) if v["calls"] else 0,
                "fallbacks": int(v["fallbacks"]),
            }
            for k, v in by_task.items()
        ],
        "interview_costs": [
            {
                "interview_id": str(i.id),
                "title": i.title,
                "duration_seconds": c.duration_seconds,
                "llm_input_tokens": c.llm_input_tokens,
                "llm_output_tokens": c.llm_output_tokens,
                "voice_seconds": c.voice_seconds,
                "code_execution_seconds": c.code_execution_seconds,
                "storage_bytes": c.storage_bytes,
                "estimated_cost_usd": c.estimated_cost_usd,
                "estimated_cost_inr": c.estimated_cost_inr,
                "updated_at": c.updated_at,
            }
            for c, i in costs
        ],
        "avg_cost_per_interview_usd": round(avg_cost, 4),
        "unit_economics": margins,
        "fx_rate_usd_inr": fx_rate(),
    }


# ----------------------------------------------------------------------------- question bank
class QuestionIn(BaseModel):
    bank_key: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9\-]+$")
    topic: str
    kind: str = Field(default="technical", pattern="^(technical|behavioral|introduction|system_design)$")
    difficulty: int = Field(ge=1, le=3)
    text: str = Field(min_length=10, max_length=2000)
    concepts: list[dict[str, Any]] = []
    followups: list[dict[str, Any]] = []
    roles: list[str] = []
    is_active: bool = True


def q_out(q: Question) -> dict[str, Any]:
    return {
        "id": str(q.id),
        "bank_key": q.bank_key,
        "topic": q.topic,
        "kind": q.kind,
        "difficulty": q.difficulty,
        "text": q.text,
        "concepts": q.concepts,
        "followups": q.followups,
        "roles": q.roles,
        "is_active": q.is_active,
        "organization_id": str(q.organization_id) if q.organization_id else None,
    }


@router.get("/questions")
async def list_questions(_: SuperAdmin, db: DB, topic: str = "", q: str = "") -> dict[str, Any]:
    stmt = select(Question)
    if topic:
        stmt = stmt.where(Question.topic == topic)
    if q:
        stmt = stmt.where(func.lower(Question.text).like(f"%{q.lower()}%"))
    rows = (await db.execute(stmt.order_by(Question.topic, Question.difficulty))).scalars().all()
    return {"items": [q_out(r) for r in rows], "topics": [{"key": t.key, "label": t.label} for t in TOPICS.values()]}


def _validate_q(body: QuestionIn) -> None:
    if body.topic not in TOPICS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown topic.")
    for c in body.concepts:
        if not isinstance(c.get("name"), str) or not isinstance(c.get("keywords"), list):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Concepts need a name and a keywords list.")
    for f in body.followups:
        if f.get("type") not in ("clarification", "challenge", "edge_case", "optimization", "architecture", "behavioral") or not f.get("text"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid follow-up.")
        f.setdefault("trigger", "any")


@router.post("/questions", status_code=201)
async def create_question(body: QuestionIn, admin: SuperAdmin, db: DB) -> dict[str, Any]:
    _validate_q(body)
    if (await db.execute(select(Question).where(Question.bank_key == body.bank_key))).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "A question with this key already exists.")
    q = Question(**body.model_dump())
    db.add(q)
    audit(db, "admin.question_create", admin.id, target_type="question", target_id=body.bank_key)
    await db.commit()
    orchestrator._bank_cache.clear()
    return q_out(q)


@router.put("/questions/{qid}")
async def update_question(qid: uuid.UUID, body: QuestionIn, admin: SuperAdmin, db: DB) -> dict[str, Any]:
    _validate_q(body)
    q = await db.get(Question, qid)
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found.")
    for k, v in body.model_dump().items():
        setattr(q, k, v)
    audit(db, "admin.question_update", admin.id, target_type="question", target_id=body.bank_key)
    await db.commit()
    orchestrator._bank_cache.clear()
    return q_out(q)


@router.delete("/questions/{qid}")
async def delete_question(qid: uuid.UUID, admin: SuperAdmin, db: DB) -> dict[str, bool]:
    q = await db.get(Question, qid)
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found.")
    await db.delete(q)
    audit(db, "admin.question_delete", admin.id, target_type="question", target_id=q.bank_key)
    await db.commit()
    orchestrator._bank_cache.clear()
    return {"ok": True}


# ----------------------------------------------------------------------------- billing config
@router.get("/billing")
async def billing(_: SuperAdmin, db: DB) -> dict[str, Any]:
    plans = (await db.execute(select(Plan).order_by(Plan.sort_order))).scalars().all()
    subs = (await db.execute(select(Plan.key, func.count(Subscription.id)).join(Subscription).group_by(Plan.key))).all()
    return {
        "plans": [
            {
                "id": str(p.id),
                "key": p.key,
                "name": p.name,
                "audience": p.audience,
                "price_monthly_usd": p.price_monthly_usd,
                "price_monthly_inr": p.price_monthly_inr,
                "limits": p.limits,
                "features": p.features,
                "is_public": p.is_public,
            }
            for p in plans
        ],
        "subscriptions": {k: int(v) for k, v in subs},
        "pricing": pricing().model_dump(),
        "fx_rate_usd_inr": fx_rate(),
        "note": "Payments are not processed yet. Plans and limits are enforced for usage only.",
    }


class PlanIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    price_monthly_usd: float = Field(ge=0)
    price_monthly_inr: float = Field(ge=0)
    limits: dict[str, int | None]
    features: list[str]
    is_public: bool = True


@router.put("/billing/plans/{plan_id}")
async def update_plan(plan_id: uuid.UUID, body: PlanIn, admin: SuperAdmin, db: DB) -> dict[str, bool]:
    p = await db.get(Plan, plan_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found.")
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    audit(db, "admin.plan_update", admin.id, target_type="plan", target_id=p.key)
    await db.commit()
    return {"ok": True}


class PricingIn(BaseModel):
    pricing: PricingConfig
    usd_inr: float = Field(gt=0, lt=1000)


@router.put("/billing/pricing")
async def update_pricing(body: PricingIn, admin: SuperAdmin, db: DB) -> dict[str, Any]:
    for key, value in (("pricing", body.pricing.model_dump()), ("fx", {"usd_inr": body.usd_inr})):
        row = await db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    audit(db, "admin.pricing_update", admin.id, usd_inr=body.usd_inr)
    await db.commit()
    await load_pricing_overrides(db)
    await load_fx_override(db)
    return {"ok": True, "pricing": pricing().model_dump(), "fx_rate_usd_inr": fx_rate()}


@router.get("/audit-logs")
async def audit_logs(_: SuperAdmin, db: DB, limit: int = 100) -> dict[str, Any]:
    rows = (await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500)))).scalars().all()
    return {
        "items": [
            {
                "action": a.action,
                "actor_id": str(a.actor_id) if a.actor_id else None,
                "organization_id": str(a.organization_id) if a.organization_id else None,
                "target_type": a.target_type,
                "target_id": a.target_id,
                "ip": a.ip,
                "details": a.details,
                "created_at": a.created_at,
            }
            for a in rows
        ]
    }


__all__ = ["get_settings", "router"]
