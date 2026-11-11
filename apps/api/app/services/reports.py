"""Final report generation from persisted evaluations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CodeExecution, Evaluation, Interview, InterviewQuestion, Report
from app.services.ai import get_ai_client
from app.services.audit import track
from app.services.usage import flush, recompute_cost, usage_scope
from intervue_engine import TOPICS, InterviewPlan, InterviewState, topic_label
from intervue_eval import AnswerRecord, AnswerScore, TimeStats, build_report

KIND_WEIGHT = {"primary": 1.0, "design": 1.4, "followup": 0.6, "coding": 1.5, "code_review": 0.7}


async def generate_report(db: AsyncSession, interview: Interview) -> Report:
    plan = InterviewPlan.model_validate(interview.plan)
    state = InterviewState.model_validate(interview.state) if interview.state else None
    rows = (
        await db.execute(
            select(Evaluation, InterviewQuestion)
            .join(InterviewQuestion, InterviewQuestion.id == Evaluation.question_id)
            .where(Evaluation.interview_id == interview.id)
            .order_by(Evaluation.created_at)
        )
    ).all()
    records = [
        AnswerRecord(
            question=q.text,
            topic=q.topic,
            topic_label="Communication" if q.topic == "introduction" else topic_label(q.topic),
            round_kind=e.round_kind,
            kind=q.kind,
            score=AnswerScore.model_validate(e.data),
            weight=KIND_WEIGHT.get(q.kind, 1.0),
        )
        for e, q in rows
    ]
    weights = {w.topic: w.weight for w in plan.skill_weights}
    submits = (
        (
            await db.execute(
                select(CodeExecution).where(CodeExecution.interview_id == interview.id, CodeExecution.kind == "submit").order_by(CodeExecution.created_at)
            )
        )
        .scalars()
        .all()
    )
    runs = (await db.execute(select(CodeExecution).where(CodeExecution.interview_id == interview.id))).scalars().all()
    coding_summary: list[dict[str, Any]] = [
        {
            "language": s.language,
            "problem": s.result.get("problem_title", ""),
            "passed": s.passed,
            "total": s.total,
            "status": s.status,
            "runtime_ms": s.runtime_ms,
            "runs": sum(1 for r in runs if r.code_session_id == s.code_session_id),
        }
        for s in submits
    ]
    started = interview.started_at or interview.created_at
    ended = interview.completed_at or datetime.now(UTC)
    actual = max(0.0, (ended - started).total_seconds() / 60)
    rounds_completed = state.rounds_completed if state else 0
    time_stats = TimeStats(
        planned_minutes=plan.duration_minutes,
        actual_minutes=actual,
        rounds_planned=len(plan.rounds),
        rounds_completed=rounds_completed,
        ended_early=bool(state and state.end_reason == "candidate"),
    )
    hints = {k: list(t.practice) for k, t in TOPICS.items()}
    with usage_scope(interview.candidate_id, interview.organization_id, interview.id) as scope:
        report_data, _ = await build_report(records, time_stats, weights, hints, coding_summary, get_ai_client())
        flush(db, scope)
    existing = (await db.execute(select(Report).where(Report.interview_id == interview.id))).scalar_one_or_none()
    if existing:
        existing.overall_score = report_data.overall_score
        existing.data = report_data.model_dump()
        report = existing
    else:
        report = Report(interview_id=interview.id, overall_score=report_data.overall_score, data=report_data.model_dump())
        db.add(report)
    interview.overall_score = report_data.overall_score
    interview.status = "completed"
    interview.completed_at = interview.completed_at or ended
    await db.flush()
    await recompute_cost(db, interview)
    track(db, "report_generated", interview.candidate_id, interview.organization_id, interview.id, score=report_data.overall_score)
    return report


def report_id(report: Report) -> uuid.UUID:
    return report.id
