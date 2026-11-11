from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import get_settings
from app.deps import DB, CurrentUser, client_ip, load_interview
from app.models import (
    CodeExecution,
    CodeSession,
    DesignSession,
    Interview,
    InterviewTemplate,
    JobDescription,
    Report,
    Resume,
    ScreenEvent,
    Transcript,
    utcnow,
)
from app.services import orchestrator
from app.services.audit import audit, track
from app.services.coding import worker_client
from app.services.interviews import create_interview, enforce_limits
from app.services.metrics import metrics
from app.services.screen import analyze_snapshot, compress
from app.services.storage import get_storage, new_key
from app.services.usage import flush, pricing, record, usage_scope
from intervue_coding import (
    WorkerUnavailable,
    get_problem,
    get_sql_problem,
    grade_code,
    grade_sql,
)
from intervue_coding.sql_engine import SqlResult
from intervue_engine import INTERVIEW_TYPES, ROLES, InterviewState, Phase
from intervue_eval import CodeFailure, CodeSubmissionSummary, DesignSummary
from intervue_security import FileValidationError, encode_token, validate_upload
from intervue_security.files import IMAGE_TYPES

router = APIRouter(prefix="/api/interviews", tags=["interviews"])


class CreateInterviewIn(BaseModel):
    role_key: str
    interview_type: str = "full"
    duration_minutes: int = Field(default=45, ge=10, le=90)
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    resume_id: uuid.UUID | None = None
    jd_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None


def interview_summary(iv: Interview) -> dict[str, Any]:
    return {
        "id": str(iv.id),
        "title": iv.title,
        "role_key": iv.role_key,
        "role_title": iv.plan.get("role_title"),
        "interview_type": iv.interview_type,
        "duration_minutes": iv.duration_minutes,
        "difficulty": iv.difficulty,
        "status": iv.status,
        "overall_score": iv.overall_score,
        "is_demo": iv.is_demo,
        "organization_id": str(iv.organization_id) if iv.organization_id else None,
        "created_at": iv.created_at,
        "started_at": iv.started_at,
        "completed_at": iv.completed_at,
    }


def interview_detail(iv: Interview) -> dict[str, Any]:
    state = InterviewState.model_validate(iv.state) if iv.state else None
    return {
        **interview_summary(iv),
        "plan": iv.plan,
        "analysis": iv.analysis,
        "consent": iv.consent,
        "live": orchestrator.public_state(iv, state),
    }


@router.get("")
async def list_interviews(user: CurrentUser, db: DB, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    rows = (
        (
            await db.execute(
                select(Interview).where(Interview.candidate_id == user.id).order_by(Interview.created_at.desc()).limit(min(limit, 100)).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return {"items": [interview_summary(r) for r in rows]}


@router.post("", status_code=201)
async def create(body: CreateInterviewIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    if body.role_key not in ROLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown role.")
    if body.interview_type not in INTERVIEW_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown interview type.")
    resume = await db.get(Resume, body.resume_id) if body.resume_id else None
    if resume and resume.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found.")
    jd = await db.get(JobDescription, body.jd_id) if body.jd_id else None
    if jd and jd.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job description not found.")
    template = await db.get(InterviewTemplate, body.template_id) if body.template_id else None
    if template and template.organization_id is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization templates are only available through an invite link.")
    if resume is None:
        resume = (await db.execute(select(Resume).where(Resume.user_id == user.id).order_by(Resume.created_at.desc()).limit(1))).scalar_one_or_none()
    await enforce_limits(db, org_id=None, user=user)
    iv = await create_interview(
        db,
        user,
        role_key=body.role_key,
        interview_type=body.interview_type,
        duration_minutes=body.duration_minutes,
        difficulty=body.difficulty,
        resume=resume,
        jd=jd,
        template=template,
        is_demo=user.is_demo,
    )
    await db.commit()
    return interview_detail(iv)


@router.get("/{interview_id}")
async def get_interview(interview_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    return interview_detail(await load_interview(db, interview_id, user))


@router.delete("/{interview_id}")
async def delete_interview(interview_id: uuid.UUID, request: Request, user: CurrentUser, db: DB) -> dict[str, bool]:
    iv = await load_interview(db, interview_id, user, candidate_only=True)
    if iv.status == "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, "End the interview before deleting it.")
    for ev in (await db.execute(select(ScreenEvent).where(ScreenEvent.interview_id == iv.id))).scalars():
        if ev.storage_key:
            await get_storage().delete(ev.storage_key)
    audit(db, "interview.delete", user.id, iv.organization_id, "interview", str(iv.id), client_ip(request))
    await db.delete(iv)
    await db.commit()
    return {"ok": True}


class ConsentIn(BaseModel):
    microphone: bool
    ai_processing: bool
    screen_share: bool = False
    camera: bool = False
    data_retention_ack: bool


@router.post("/{interview_id}/consent")
async def consent(interview_id: uuid.UUID, body: ConsentIn, request: Request, user: CurrentUser, db: DB) -> dict[str, Any]:
    iv = await load_interview(db, interview_id, user, candidate_only=True)
    if not (body.ai_processing and body.data_retention_ack):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "AI processing and data handling consent are required to start.")
    iv.consent = {**body.model_dump(), "accepted": True, "accepted_at": utcnow().isoformat(), "ip": client_ip(request)}
    audit(db, "interview.consent", user.id, iv.organization_id, "interview", str(iv.id), client_ip(request), **body.model_dump())
    await db.commit()
    return {"ok": True, "consent": iv.consent}


@router.post("/{interview_id}/ws-ticket")
async def ws_ticket(interview_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    iv = await load_interview(db, interview_id, user, candidate_only=True)
    s = get_settings()
    ticket = encode_token(s.auth_secret, str(user.id), "ws", 120, {"iid": str(iv.id)})
    voice = orchestrator.get_voice_provider().session_config()
    return {"ticket": ticket, "ws_url": s.public_api_url.replace("http", "ws", 1) + f"/ws/interviews/{iv.id}", "voice": voice.__dict__}


@router.get("/{interview_id}/transcript")
async def transcript(interview_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    iv = await load_interview(db, interview_id, user)
    rows = (await db.execute(select(Transcript).where(Transcript.interview_id == iv.id).order_by(Transcript.sequence))).scalars().all()
    return {"items": [{"speaker": t.speaker, "kind": t.kind, "text": t.text, "at": t.created_at} for t in rows]}


@router.get("/{interview_id}/report")
async def report(interview_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    iv = await load_interview(db, interview_id, user)
    rep = (await db.execute(select(Report).where(Report.interview_id == iv.id))).scalar_one_or_none()
    if rep is None:
        if iv.status in ("evaluating", "in_progress"):
            raise HTTPException(status.HTTP_409_CONFLICT, "The report is still being generated.")
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No report yet. Complete the interview first.")
    return {"interview": interview_summary(iv), "plan": iv.plan, "report": rep.data, "generated_at": rep.created_at}


@router.post("/{interview_id}/report/regenerate")
async def regenerate_report(interview_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    iv = await load_interview(db, interview_id, user)
    if iv.status not in ("completed", "evaluating"):
        raise HTTPException(status.HTTP_409_CONFLICT, "The interview hasn't finished yet.")
    await orchestrator.finalize(iv.id) if iv.status == "evaluating" else None
    from app.services.reports import generate_report

    if iv.status == "completed":
        await generate_report(db, iv)
        await db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------- coding
class CodeIn(BaseModel):
    code: str = Field(max_length=100_000)
    language: str


async def _active_coding(db: DB, iv: Interview) -> tuple[InterviewState, CodeSession]:
    if iv.status != "in_progress" or not iv.state:
        raise HTTPException(status.HTTP_409_CONFLICT, "The interview is not in progress.")
    state = InterviewState.model_validate(iv.state)
    cs = state.code_state
    if cs is None or state.phase != Phase.CODING:
        raise HTTPException(status.HTTP_409_CONFLICT, "There is no active coding question.")
    sess = (await db.execute(select(CodeSession).where(CodeSession.interview_id == iv.id, CodeSession.problem_id == cs.problem_id))).scalar_one_or_none()
    if sess is None:
        sess = CodeSession(interview_id=iv.id, problem_id=cs.problem_id, language=cs.language, is_sql=cs.is_sql)
        db.add(sess)
        await db.flush()
    return state, sess


async def _execute(iv: Interview, state: InterviewState, code: str, language: str, include_hidden: bool) -> tuple[Any, dict[str, Any], str]:
    cs = state.code_state
    assert cs is not None
    client = worker_client()
    started = time.perf_counter()
    try:
        if cs.is_sql:
            sp = get_sql_problem(cs.problem_id)
            assert sp is not None
            cand = SqlResult.model_validate(await client.sql(sp.dataset, code))
            ref = SqlResult.model_validate(await client.sql(sp.dataset, sp.reference_sql))
            grade = grade_sql(sp, cand, ref)
            payload = {"columns": cand.columns, "rows": cand.rows[:100], "truncated": cand.truncated or len(cand.rows) > 100, "backend": "sqlite-sandbox"}
            title = sp.title
        else:
            p = get_problem(cs.problem_id)
            assert p is not None
            if language not in p.starter:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported language for this problem.")
            tests = [t.model_dump() for t in p.tests if include_hidden or not t.hidden]
            wr = await client.execute(language, code, p.function_name, tests, 6000)
            grade = grade_code(p, wr, include_hidden)
            payload = {"backend": wr.get("backend", ""), "stderr": (wr.get("stderr") or "")[-2000:]}
            title = p.title
    except WorkerUnavailable as exc:
        metrics.error("worker", str(exc))
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The code runner is unavailable right now. Please try again in a moment.") from exc
    ms = (time.perf_counter() - started) * 1000
    metrics.observe("execution", ms)
    return grade, payload, title


@router.post("/{interview_id}/code/run")
async def run_code(interview_id: uuid.UUID, body: CodeIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    iv = await load_interview(db, interview_id, user, candidate_only=True)
    state, sess = await _active_coding(db, iv)
    grade, payload, title = await _execute(iv, state, body.code, body.language, include_hidden=False)
    sess.code, sess.language, sess.run_count = body.code, body.language, sess.run_count + 1
    with usage_scope(user.id, iv.organization_id, iv.id) as scope:
        record("execution", payload.get("backend") or "worker", grade.runtime_ms / 1000, pricing().execution_cost(grade.runtime_ms / 1000), task="run")
        flush(db, scope)
    db.add(
        CodeExecution(
            code_session_id=sess.id,
            interview_id=iv.id,
            kind="run",
            language=body.language,
            code=body.code,
            status=grade.status,
            passed=grade.passed,
            total=grade.total,
            result={**grade.model_dump(), **payload, "problem_title": title},
            runtime_ms=grade.runtime_ms,
            backend=str(payload.get("backend", "")),
        )
    )
    track(db, "code_run", user.id, iv.organization_id, iv.id, status=grade.status)
    await db.commit()
    await orchestrator.update_code_state(iv.id, body.code, {"status": grade.status, "passed": grade.passed, "total": grade.total})
    await orchestrator.hub.send(
        str(iv.id), orchestrator.event("CODE_EXECUTED", iv.id, {"kind": "run", "status": grade.status, "passed": grade.passed, "total": grade.total})
    )
    return {"kind": "run", **grade.model_dump(), **payload}


@router.post("/{interview_id}/code/submit")
async def submit_code(interview_id: uuid.UUID, body: CodeIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    iv = await load_interview(db, interview_id, user, candidate_only=True)
    state, sess = await _active_coding(db, iv)
    grade, payload, title = await _execute(iv, state, body.code, body.language, include_hidden=True)
    sess.code, sess.language, sess.submitted_at = body.code, body.language, utcnow()
    db.add(
        CodeExecution(
            code_session_id=sess.id,
            interview_id=iv.id,
            kind="submit",
            language=body.language,
            code=body.code,
            status=grade.status,
            passed=grade.passed,
            total=grade.total,
            result={**grade.model_dump(), **payload, "problem_title": title},
            runtime_ms=grade.runtime_ms,
            backend=str(payload.get("backend", "")),
        )
    )
    with usage_scope(user.id, iv.organization_id, iv.id) as scope:
        record("execution", payload.get("backend") or "worker", grade.runtime_ms / 1000, pricing().execution_cost(grade.runtime_ms / 1000), task="submit")
        flush(db, scope)
    await db.commit()
    cs = state.code_state
    assert cs is not None
    statement = get_sql_problem(cs.problem_id).statement if cs.is_sql else get_problem(cs.problem_id).statement  # type: ignore[union-attr]
    features = get_sql_problem(cs.problem_id).expected_features if cs.is_sql else []  # type: ignore[union-attr]
    failures = [
        CodeFailure(
            name=o.name,
            input=str(o.args) if o.args is not None else "hidden",
            expected=str(o.expected) if o.expected is not None else "hidden",
            actual=str(o.actual) if o.actual is not None else (o.error or "hidden"),
        )
        for o in grade.outcomes
        if not o.passed
    ]
    summary = CodeSubmissionSummary(
        language=body.language,
        code=body.code,
        problem_id=cs.problem_id,
        problem_title=title,
        passed=grade.passed,
        total=grade.total,
        status=grade.status if grade.status in ("passed", "failed", "error", "timeout") else "error",  # type: ignore[arg-type]
        error=grade.error,
        runtime_ms=grade.runtime_ms,
        run_count=sess.run_count + 1,
        failures=failures,
        expected_features=features,
    )
    await orchestrator.hub.send(
        str(iv.id), orchestrator.event("CODE_EXECUTED", iv.id, {"kind": "submit", "status": grade.status, "passed": grade.passed, "total": grade.total})
    )
    await orchestrator.submit_code(iv.id, user, summary, statement)
    return {"kind": "submit", **grade.model_dump(), **payload}


@router.get("/{interview_id}/code")
async def code_history(interview_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    iv = await load_interview(db, interview_id, user)
    sessions = (await db.execute(select(CodeSession).where(CodeSession.interview_id == iv.id).order_by(CodeSession.created_at))).scalars().all()
    execs = (await db.execute(select(CodeExecution).where(CodeExecution.interview_id == iv.id).order_by(CodeExecution.created_at))).scalars().all()
    out = []
    for s in sessions:
        problem = get_sql_problem(s.problem_id) if s.is_sql else get_problem(s.problem_id)
        out.append(
            {
                "id": str(s.id),
                "problem_id": s.problem_id,
                "title": problem.title if problem else s.problem_id,
                "statement": problem.statement if problem else "",
                "language": s.language,
                "is_sql": s.is_sql,
                "code": s.code,
                "submitted_at": s.submitted_at,
                "executions": [
                    {
                        "kind": e.kind,
                        "status": e.status,
                        "passed": e.passed,
                        "total": e.total,
                        "runtime_ms": e.runtime_ms,
                        "created_at": e.created_at,
                        "backend": e.backend,
                    }
                    for e in execs
                    if e.code_session_id == s.id
                ],
            }
        )
    return {"sessions": out}


# ----------------------------------------------------------------------------- system design
@router.put("/{interview_id}/design")
async def save_design(interview_id: uuid.UUID, body: DesignSummary, user: CurrentUser, db: DB) -> dict[str, Any]:
    iv = await load_interview(db, interview_id, user, candidate_only=True)
    if len(body.nodes) > 60 or len(body.edges) > 120 or len(body.notes) > 5000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Design is too large.")
    ds = (await db.execute(select(DesignSession).where(DesignSession.interview_id == iv.id))).scalar_one_or_none()
    if ds is None:
        ds = DesignSession(interview_id=iv.id)
        db.add(ds)
    ds.graph = body.model_dump()
    await db.commit()
    return {"ok": True, "summary": body.as_text()}


@router.get("/{interview_id}/design")
async def get_design(interview_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    iv = await load_interview(db, interview_id, user)
    ds = (await db.execute(select(DesignSession).where(DesignSession.interview_id == iv.id))).scalar_one_or_none()
    return {"graph": ds.graph if ds else None}


# ----------------------------------------------------------------------------- screen sharing
@router.post("/{interview_id}/screen-events", status_code=201)
async def screen_event(
    interview_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    event_type: str = Form(..., pattern="^(started|stopped|snapshot|denied)$"),
    reason: str = Form("", max_length=40),
    image: UploadFile | None = File(None),
) -> dict[str, Any]:
    iv = await load_interview(db, interview_id, user, candidate_only=True)
    if event_type in ("started", "snapshot") and not iv.consent.get("screen_share"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Screen sharing consent was not given for this interview.")
    ev = ScreenEvent(interview_id=iv.id, event_type=event_type, reason=reason)
    out: dict[str, Any] = {"event_type": event_type}
    if event_type == "snapshot":
        if image is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Snapshot image is required.")
        data = await image.read(3 * 1024 * 1024 + 1)
        try:
            validate_upload(image.filename or "snapshot.jpg", data, IMAGE_TYPES, 3 * 1024 * 1024)
            jpeg, w, h = compress(data)
        except (FileValidationError, OSError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid snapshot image.") from exc
        key = new_key(f"snapshots/{iv.id}", ".jpg")
        await get_storage().put(key, jpeg, "image/jpeg")
        with usage_scope(user.id, iv.organization_id, iv.id) as scope:
            analysis = await analyze_snapshot(jpeg, w, h, reason or "candidate shared")
            record("storage", get_storage().name, len(jpeg), pricing().storage_cost(len(jpeg)), task="snapshot")
            flush(db, scope)
        ev.storage_key, ev.width, ev.height, ev.size_bytes, ev.analysis = key, w, h, len(jpeg), analysis.model_dump()
        out.update(width=w, height=h, size_bytes=len(jpeg), analysis=analysis.model_dump())
    db.add(ev)
    if event_type in ("started", "stopped"):
        track(db, f"screen_share_{event_type}", user.id, iv.organization_id, iv.id)
    await db.commit()
    etype = {"started": "SCREEN_SHARE_STARTED", "stopped": "SCREEN_SHARE_STOPPED", "snapshot": "SCREEN_SNAPSHOT_RECEIVED", "denied": "SCREEN_SHARE_DENIED"}[
        event_type
    ]
    await orchestrator.hub.send(str(iv.id), orchestrator.event(etype, iv.id, {k: v for k, v in out.items() if k != "analysis"}))
    return out
