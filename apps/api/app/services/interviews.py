"""Interview creation: resume/JD analysis, plan generation, persistence and limit checks."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CandidateProfile,
    Interview,
    InterviewRound,
    InterviewTemplate,
    JobDescription,
    OrganizationLimit,
    Plan,
    Question,
    Resume,
    Subscription,
    User,
)
from app.services.ai import get_ai_client
from app.services.audit import track
from app.services.usage import flush, usage_scope
from intervue_engine import QUESTIONS, BankQuestion, analyze, build_plan, get_role


async def load_bank(db: AsyncSession, organization_id: uuid.UUID | None) -> list[BankQuestion]:
    q = select(Question).where(Question.is_active.is_(True))
    q = (
        q.where(or_(Question.organization_id.is_(None), Question.organization_id == organization_id))
        if organization_id
        else q.where(Question.organization_id.is_(None))
    )
    rows = (await db.execute(q)).scalars().all()
    if not rows:
        return list(QUESTIONS)
    return [
        BankQuestion(id=r.bank_key, topic=r.topic, difficulty=r.difficulty, text=r.text, concepts=r.concepts, followups=r.followups, roles=r.roles, kind=r.kind)
        for r in rows
    ]


async def _monthly_interviews(db: AsyncSession, *, org_id: uuid.UUID | None, user_id: uuid.UUID | None) -> int:
    start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    q = select(func.count(Interview.id)).where(Interview.created_at >= start)
    q = q.where(Interview.organization_id == org_id) if org_id else q.where(Interview.candidate_id == user_id, Interview.organization_id.is_(None))
    return int((await db.execute(q)).scalar_one())


async def interview_limit(db: AsyncSession, *, org_id: uuid.UUID | None, user_id: uuid.UUID | None) -> int | None:
    if org_id:
        lim = (await db.execute(select(OrganizationLimit).where(OrganizationLimit.organization_id == org_id))).scalar_one_or_none()
        if lim and lim.interviews_per_month is not None:
            return lim.interviews_per_month
        sub = (await db.execute(select(Subscription, Plan).join(Plan).where(Subscription.organization_id == org_id))).first()
    else:
        sub = (await db.execute(select(Subscription, Plan).join(Plan).where(Subscription.user_id == user_id))).first()
        if sub is None:
            free = (await db.execute(select(Plan).where(Plan.key == "free"))).scalar_one_or_none()
            return int(free.limits.get("interviews_per_month")) if free and free.limits.get("interviews_per_month") is not None else None
    if sub is None:
        return None
    v = sub[1].limits.get("interviews_per_month")
    return int(v) if v is not None else None


async def enforce_limits(db: AsyncSession, *, org_id: uuid.UUID | None, user: User) -> None:
    if user.role == "super_admin" or user.is_demo:
        return
    limit = await interview_limit(db, org_id=org_id, user_id=user.id)
    if limit is None:
        return
    used = await _monthly_interviews(db, org_id=org_id, user_id=user.id)
    if used >= limit:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, f"Monthly interview limit reached ({limit}). Upgrade your plan or try again next month.")


async def create_interview(
    db: AsyncSession,
    user: User,
    *,
    role_key: str,
    interview_type: str,
    duration_minutes: int,
    difficulty: str,
    resume: Resume | None = None,
    jd: JobDescription | None = None,
    template: InterviewTemplate | None = None,
    organization_id: uuid.UUID | None = None,
    invite_id: uuid.UUID | None = None,
    is_demo: bool = False,
    title: str | None = None,
) -> Interview:
    role = get_role(role_key)
    profile = (await db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id))).scalar_one_or_none()
    jd_text = (jd.text if jd else "") or (template.jd_text if template else "")
    interview_id = uuid.uuid4()
    with usage_scope(user.id, organization_id, None) as scope:
        if organization_id:
            # RAG: organisation guidelines / role descriptions shape the analysis and topic priorities
            from app.services.rag import retrieve

            hits = await retrieve(db, organization_id, f"{role.title} interview {jd_text[:500]}", k=3)
            if hits:
                jd_text = (jd_text + "\n\nOrganization interview guidance:\n" + "\n---\n".join(c.content for _, c in hits)).strip()
        analysis, _ = await analyze(
            get_ai_client(),
            resume.text if resume else "",
            jd_text,
            role.key,
            profile.experience_years if profile else None,
            difficulty,
        )
        template_rounds: list[dict[str, Any]] | None = template.rounds if template and template.rounds else None
        plan = build_plan(role.key, interview_type, duration_minutes, difficulty, analysis, template_rounds)
        if template and template.scoring_weights:
            # organisation-defined scoring weights override time-based weights
            total = sum(max(0.0, float(v)) for v in template.scoring_weights.values()) or 1.0
            from intervue_engine.schemas import SkillWeight
            from intervue_engine.taxonomy import topic_label as _label

            plan.skill_weights = [
                SkillWeight(topic=k, label=_label(k), weight=round(max(0.0, float(v)) / total, 3))
                for k, v in sorted(template.scoring_weights.items(), key=lambda kv: -float(kv[1]))
            ]
        interview = Interview(
            id=interview_id,
            candidate_id=user.id,
            organization_id=organization_id,
            template_id=template.id if template else None,
            invite_id=invite_id,
            resume_id=resume.id if resume else None,
            jd_id=jd.id if jd else None,
            role_key=role.key,
            title=title or f"{role.title} — {plan.interview_type.replace('_', ' ').title()} interview",
            interview_type=plan.interview_type,
            duration_minutes=plan.duration_minutes,
            difficulty=plan.difficulty,
            status="planned",
            plan=plan.model_dump(),
            analysis=analysis.model_dump(),
            state={},
            is_demo=is_demo,
        )
        db.add(interview)
        await db.flush()
        for rec in scope.records:
            rec.interview_id = interview.id
        flush(db, scope)
    for i, r in enumerate(plan.rounds):
        db.add(InterviewRound(interview_id=interview.id, round_key=r.id, ordinal=i, kind=r.kind, title=r.title, minutes=r.minutes))
    track(db, "interview_created", user.id, organization_id, interview.id, role=role.key, type=plan.interview_type)
    return interview
