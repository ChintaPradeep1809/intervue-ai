"""Real-time interview orchestration.

Bridges WebSocket/REST input to the `InterviewEngine`, persists everything the engine produces
(questions, responses, evaluations, transcript, state) and broadcasts events to connected clients.
One asyncio lock per interview serialises all state changes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import session_factory
from app.logging_setup import interview_id_var
from app.models import (
    CodeExecution,
    DesignSession,
    Evaluation,
    Interview,
    InterviewQuestion,
    InterviewRound,
    JobDescription,
    Response,
    ScreenEvent,
    Transcript,
    User,
    utcnow,
)
from app.services.ai import get_ai_client, get_voice_provider
from app.services.audit import track
from app.services.interviews import load_bank
from app.services.metrics import metrics
from app.services.usage import flush, pricing, record, usage_scope
from intervue_coding import get_problem, get_sql_problem, public_view, sql_public_view
from intervue_engine import (
    BankQuestion,
    EngineContext,
    EngineError,
    EngineOutput,
    InterviewEngine,
    InterviewPlan,
    InterviewState,
    NextAction,
    Phase,
    ResumeAnalysis,
    build_toolspecs,
)
from intervue_eval import CodeSubmissionSummary, DesignSummary

log = logging.getLogger("intervue.orchestrator")


def now_ts() -> float:
    return time.time()


def event(event_type: str, interview_id: uuid.UUID | str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"event_type": event_type, "interview_id": str(interview_id), "timestamp": datetime.now(UTC).isoformat(), "payload": payload or {}}


class Hub:
    def __init__(self) -> None:
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)

    def add(self, iid: str, ws: WebSocket) -> None:
        self.connections[iid].add(ws)

    def remove(self, iid: str, ws: WebSocket) -> None:
        self.connections[iid].discard(ws)
        if not self.connections[iid]:
            self.connections.pop(iid, None)

    async def send(self, iid: str, msg: dict[str, Any]) -> None:
        dead = []
        for ws in list(self.connections.get(iid, ())):
            try:
                await ws.send_text(json.dumps(msg, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remove(iid, ws)

    def active_interviews(self) -> int:
        return len(self.connections)


hub = Hub()
_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_bank_cache: dict[str, list[BankQuestion]] = {}
_background: set[asyncio.Task[None]] = set()  # strong refs so report tasks aren't garbage-collected
_pending: dict[str, set[asyncio.Task[None]]] = defaultdict(set)
_tts_disabled_until = [0.0]  # circuit breaker for server TTS (quota exhausted, bad key)  # background score refinements per interview


def _build_engine() -> InterviewEngine:
    from app.services.ai import get_fast_ai_client

    main = get_ai_client()
    # With a real LLM, answers are routed on an instant deterministic score and the LLM score is
    # refined in the background, so the candidate never waits for evaluation between questions.
    return InterviewEngine(main, max_followups=get_settings().max_followups, fast_ai=get_fast_ai_client(), defer_scoring=not main.primary.is_mock)


engine = _build_engine()


def reset_runtime() -> None:
    """Tests: rebuild the engine after settings/provider changes."""
    global engine
    _bank_cache.clear()
    engine = _build_engine()


# ------------------------------------------------------------------------ public state
def problem_view(state: InterviewState) -> dict[str, Any] | None:
    cs = state.code_state
    if cs is None:
        return None
    if cs.is_sql:
        sp = get_sql_problem(cs.problem_id)
        return sql_public_view(sp) if sp else None
    p = get_problem(cs.problem_id)
    return public_view(p) if p else None


def public_state(interview: Interview, state: InterviewState | None) -> dict[str, Any]:
    plan = interview.plan or {}
    rounds = plan.get("rounds", [])
    s = state
    round_status = []
    for i, r in enumerate(rounds):
        st = "pending"
        if s and i < s.round_index:
            st = "completed"
        elif s and i == s.round_index:
            st = "completed" if s.phase in (Phase.FINAL_EVALUATION, Phase.COMPLETED) else "active"
        round_status.append({"id": r["id"], "kind": r["kind"], "title": r["title"], "minutes": r["minutes"], "status": st})
    cur = s.current_question if s else None
    current_round = rounds[s.round_index] if s and 0 <= s.round_index < len(rounds) else None
    return {
        "status": interview.status,
        "phase": s.phase if s else Phase.INTERVIEW_SETUP,
        "next_action": s.next_action if s else NextAction.START,
        "rounds": round_status,
        "round_index": s.round_index if s else -1,
        "current_round": current_round,
        "question": {"text": cur.text, "kind": cur.kind, "topic": cur.topic, "followup_type": cur.followup_type} if cur else None,
        "question_index": s.question_index if s else 0,
        "started_at": s.started_at if s else None,
        "deadline_at": s.deadline_at if s else None,
        "server_time": now_ts(),
        "coding": (
            {
                "problem": problem_view(s),
                "language": s.code_state.language,
                "is_sql": s.code_state.is_sql,
                "code": s.code_state.code,
                "submitted": s.code_state.submitted,
                "run_count": s.code_state.run_count,
            }
            if s and s.code_state
            else None
        ),
        "design_active": bool(current_round and current_round["kind"] == "system_design" and s and s.phase not in (Phase.FINAL_EVALUATION, Phase.COMPLETED)),
        "ai_is_mock": get_ai_client().primary.is_mock,
    }


# ------------------------------------------------------------------------ helpers
async def _next_seq(db: AsyncSession, interview_id: uuid.UUID) -> int:
    v = (await db.execute(select(func.max(Transcript.sequence)).where(Transcript.interview_id == interview_id))).scalar_one()
    return int(v or 0) + 1


async def _design_text(db: AsyncSession, interview_id: uuid.UUID) -> str:
    ds = (await db.execute(select(DesignSession).where(DesignSession.interview_id == interview_id))).scalar_one_or_none()
    if not ds or not ds.graph:
        return ""
    try:
        return DesignSummary.model_validate(ds.graph).as_text()
    except Exception:
        return ""


def _tool_handlers(interview_id: uuid.UUID) -> dict[str, Any]:
    async def with_db(fn):  # type: ignore[no-untyped-def]
        async with session_factory()() as db:
            iv = await db.get(Interview, interview_id)
            return await fn(db, iv)

    async def previous_answers(args: dict[str, Any]) -> Any:
        limit = max(1, min(10, int(args.get("limit", 5))))

        async def q(db: AsyncSession, iv: Interview) -> Any:
            rows = (
                await db.execute(
                    select(Response, InterviewQuestion)
                    .join(InterviewQuestion, InterviewQuestion.id == Response.question_id)
                    .where(Response.interview_id == iv.id)
                    .order_by(Response.created_at.desc())
                    .limit(limit)
                )
            ).all()
            return [{"question": qq.text, "answer": r.answer_text[:1500]} for r, qq in rows]

        return await with_db(q)

    async def state(_: dict[str, Any]) -> Any:
        async def q(db: AsyncSession, iv: Interview) -> Any:
            ps = public_state(iv, InterviewState.model_validate(iv.state) if iv.state else None)
            return {k: ps[k] for k in ("phase", "current_round", "question", "question_index", "deadline_at", "server_time")}

        return await with_db(q)

    async def analysis(_: dict[str, Any]) -> Any:
        return await with_db(lambda db, iv: _const(iv.analysis))

    async def profile(_: dict[str, Any]) -> Any:
        async def q(db: AsyncSession, iv: Interview) -> Any:
            u = await db.get(User, iv.candidate_id)
            return {"name": u.full_name if u else None, "target_role": iv.plan.get("role_title"), "experience_level": iv.plan.get("experience_level")}

        return await with_db(q)

    async def jd(_: dict[str, Any]) -> Any:
        async def q(db: AsyncSession, iv: Interview) -> Any:
            if not iv.jd_id:
                return "No job description provided."
            j = await db.get(JobDescription, iv.jd_id)
            return (j.text if j else "")[:4000]

        return await with_db(q)

    async def code(_: dict[str, Any]) -> Any:
        async def q(db: AsyncSession, iv: Interview) -> Any:
            s = InterviewState.model_validate(iv.state)
            return {"language": s.code_state.language, "code": s.code_state.code} if s.code_state else "No code yet."

        return await with_db(q)

    async def execution(_: dict[str, Any]) -> Any:
        async def q(db: AsyncSession, iv: Interview) -> Any:
            e = (
                await db.execute(select(CodeExecution).where(CodeExecution.interview_id == iv.id).order_by(CodeExecution.created_at.desc()).limit(1))
            ).scalar_one_or_none()
            return {"status": e.status, "passed": e.passed, "total": e.total, "kind": e.kind} if e else "No executions yet."

        return await with_db(q)

    async def screen(_: dict[str, Any]) -> Any:
        async def q(db: AsyncSession, iv: Interview) -> Any:
            e = (
                await db.execute(
                    select(ScreenEvent)
                    .where(ScreenEvent.interview_id == iv.id, ScreenEvent.event_type == "snapshot")
                    .order_by(ScreenEvent.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            return e.analysis if e else "No screen snapshot shared."

        return await with_db(q)

    return {
        "get_candidate_profile": profile,
        "get_resume_analysis": analysis,
        "get_job_description": jd,
        "get_interview_state": state,
        "get_previous_answers": previous_answers,
        "get_current_code": code,
        "get_execution_result": execution,
        "analyze_screen_snapshot": screen,
    }


async def _const(v: Any) -> Any:
    return v


async def _context(db: AsyncSession, interview: Interview) -> EngineContext:
    key = f"{interview.id}"
    if key not in _bank_cache:
        _bank_cache[key] = await load_bank(db, interview.organization_id)
    user = await db.get(User, interview.candidate_id)
    tools = build_toolspecs(_tool_handlers(interview.id)) if not get_ai_client().primary.is_mock else []
    return EngineContext(
        plan=InterviewPlan.model_validate(interview.plan),
        bank=_bank_cache[key],
        now=now_ts(),
        analysis=ResumeAnalysis.model_validate(interview.analysis) if interview.analysis else None,
        candidate_name=user.full_name if user and not user.is_demo else None,
        design_text=await _design_text(db, interview.id),
        tools=tools,
    )


async def _apply(
    db: AsyncSession, interview: Interview, state: InterviewState, out: EngineOutput, refinements: list[tuple[Evaluation, dict[str, Any]]] | None = None
) -> list[dict[str, Any]]:
    """Persist engine output; return the events to broadcast after commit."""
    msgs: list[dict[str, Any]] = []
    iid = interview.id
    seq = await _next_seq(db, iid)
    base_seq = (await db.execute(select(func.count(InterviewQuestion.id)).where(InterviewQuestion.interview_id == iid))).scalar_one()
    for i, aq in enumerate(out.asked):
        row = InterviewQuestion(
            interview_id=iid,
            round_key=aq.round_id,
            qid=aq.qid,
            parent_qid=aq.parent_qid,
            kind=aq.kind,
            followup_type=aq.followup_type,
            topic=aq.topic,
            text=aq.text,
            difficulty=aq.difficulty,
            expected_concepts=aq.expected_concepts,
            sequence=int(base_seq) + i + 1,
        )
        db.add(row)
        await db.flush()
        aq.db_id = str(row.id)
        if state.current_question and state.current_question.qid == aq.qid:
            state.current_question.db_id = str(row.id)
    for sa in out.scored:
        qrow_id = uuid.UUID(sa.question.db_id) if sa.question.db_id else None
        if qrow_id is None:
            qrow = (
                await db.execute(
                    select(InterviewQuestion)
                    .where(InterviewQuestion.interview_id == iid, InterviewQuestion.qid == sa.question.qid)
                    .order_by(InterviewQuestion.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            qrow_id = qrow.id if qrow else None
        if qrow_id is None:
            continue
        kind = "code" if sa.question.kind == "coding" else "design" if sa.question.kind == "design" else "answer"
        resp = Response(interview_id=iid, question_id=qrow_id, answer_text=sa.answer, source="code" if kind == "code" else "voice")
        db.add(resp)
        await db.flush()
        round_kind = next((r["kind"] for r in interview.plan["rounds"] if r["id"] == sa.question.round_id), "technical")
        evaluation = Evaluation(
            interview_id=iid,
            question_id=qrow_id,
            response_id=resp.id,
            kind=kind,
            topic=sa.question.topic,
            round_kind=round_kind,
            score=sa.score.score,
            data=sa.score.model_dump(),
            provider=sa.provider,
            fallback_used=sa.fallback_used,
        )
        db.add(evaluation)
        if sa.refine is not None and refinements is not None:
            refinements.append((evaluation, sa.refine))
        track(db, "question_answered", interview.candidate_id, interview.organization_id, iid, topic=sa.question.topic, kind=sa.question.kind)
    rounds = {r.round_key: r for r in (await db.execute(select(InterviewRound).where(InterviewRound.interview_id == iid))).scalars()}
    for etype, payload in out.events:
        if etype == "ROUND_STARTED":
            r = rounds.get(payload["round"]["id"])
            if r:
                r.status, r.started_at = "active", utcnow()
            if payload["round"]["kind"] in ("coding", "sql"):
                track(db, "coding_started", interview.candidate_id, interview.organization_id, iid)
        elif etype == "ROUND_COMPLETED":
            r = rounds.get(payload["round_id"])
            if r:
                r.status, r.completed_at = "completed", utcnow()
        msgs.append(event(etype, iid, payload))
    if out.utterances:
        segments = []
        for u in out.utterances:
            db.add(Transcript(interview_id=iid, speaker="interviewer", kind=u.kind, text=u.text, sequence=seq))
            seq += 1
            segments.append({"text": u.text, "kind": u.kind})
        speech: dict[str, Any] = {"segments": segments}
        vp = get_voice_provider()
        if vp.session_config().tts == "server" and _tts_disabled_until[0] < time.monotonic():
            text = " ".join(s["text"] for s in segments)
            started = time.perf_counter()
            try:
                audio = await vp.synthesize(text)
                if audio:
                    speech["audio"] = {"mime_type": audio.mime_type, "b64": audio.audio_b64}
                    ms = int((time.perf_counter() - started) * 1000)
                    metrics.observe("voice:tts", ms)
                    record("tts", vp.name, len(text), pricing().voice_cost(vp.name, 0, len(text)), task="tts", latency_ms=ms)
            except Exception as exc:
                pause = float(getattr(exc, "cooldown_seconds", 600))
                metrics.error("voice", f"{exc} - server voice paused for {int(pause)} s")
                _tts_disabled_until[0] = time.monotonic() + pause
                speech["tts_error"] = "Server voice unavailable; using on-device voice."
        msgs.append(event("AI_SPEAKING", iid, speech))
    if out.finished:
        interview.status = "evaluating"
        interview.completed_at = utcnow()
    interview.state = state.model_dump(mode="json")
    msgs.append(event("STATE_SYNC", iid, public_state(interview, state)))
    return msgs


async def _broadcast(iid: str, msgs: list[dict[str, Any]]) -> None:
    for m in msgs:
        await hub.send(iid, m)


async def _run(interview_id: uuid.UUID, user: User | None, action: str, fn: Any) -> None:
    """Load → engine call → persist → commit → broadcast, under the interview lock."""
    iid = str(interview_id)
    interview_id_var.set(iid)
    async with _locks[iid]:
        async with session_factory()() as db:
            interview = await db.get(Interview, interview_id)
            if interview is None:
                return
            state = (
                InterviewState.model_validate(interview.state)
                if interview.state
                else InterviewState(interview_id=iid, candidate_id=str(interview.candidate_id), role=interview.role_key)
            )
            ctx = await _context(db, interview)
            with usage_scope(interview.candidate_id, interview.organization_id, interview.id) as scope:
                started = time.perf_counter()
                out: EngineOutput = await fn(db, interview, state, ctx)
                metrics.observe(f"engine:{action}", (time.perf_counter() - started) * 1000)
                refinements: list[tuple[Evaluation, dict[str, Any]]] = []
                msgs = await _apply(db, interview, state, out, refinements)
                flush(db, scope)
            await db.commit()
            for evaluation, payload in refinements:
                _schedule_refinement(iid, evaluation.id, payload, interview.candidate_id, interview.organization_id)
        await _broadcast(iid, msgs)
    if out.finished:
        task = asyncio.create_task(finalize(interview_id))
        _background.add(task)
        task.add_done_callback(_background.discard)


def _schedule_refinement(iid: str, evaluation_id: uuid.UUID, payload: dict[str, Any], user_id: uuid.UUID, org_id: uuid.UUID | None) -> None:
    task = asyncio.create_task(refine_evaluation(evaluation_id, payload, user_id, org_id))
    _pending[iid].add(task)
    task.add_done_callback(_pending[iid].discard)


async def refine_evaluation(evaluation_id: uuid.UUID, payload: dict[str, Any], user_id: uuid.UUID, org_id: uuid.UUID | None) -> None:
    """Replace the instant deterministic score with the LLM evaluation (off the interview's critical path)."""
    data = dict(payload)
    kind = data.pop("kind")
    try:
        async with session_factory()() as db:
            evaluation = await db.get(Evaluation, evaluation_id)
            if evaluation is None:
                return
            with usage_scope(user_id, org_id, evaluation.interview_id) as scope:
                if kind == "code":
                    score, res = await engine.evaluator.score_code(data["submission"], data["problem_statement"])
                else:
                    score, res = await engine.evaluator.score_answer(**data)
                flush(db, scope)
            evaluation.score = score.score
            evaluation.data = score.model_dump()
            evaluation.provider = res.provider
            evaluation.fallback_used = res.fallback_used
            await db.commit()
        metrics.incr("scores_refined")
    except Exception as exc:  # the deterministic score stays in place
        log.exception("score_refinement_failed")
        metrics.error("refine", str(exc))


async def finalize(interview_id: uuid.UUID) -> None:
    from app.services.reports import generate_report

    iid = str(interview_id)
    # wait for background score refinements so the report uses the final LLM scores
    pending = list(_pending.get(iid, ()))
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    try:
        async with _locks[iid]:
            async with session_factory()() as db:
                interview = await db.get(Interview, interview_id)
                if interview is None or interview.status == "completed":
                    return
                state = InterviewState.model_validate(interview.state)
                report = await generate_report(db, interview)
                if state.phase == Phase.FINAL_EVALUATION:
                    InterviewEngine.mark_completed(state)
                interview.state = state.model_dump(mode="json")
                track(db, "interview_completed", interview.candidate_id, interview.organization_id, interview.id, reason=state.end_reason)
                await db.commit()
                msgs = [
                    event("INTERVIEW_COMPLETED", iid, {"report_id": str(report.id), "overall_score_ready": True}),
                    event("STATE_SYNC", iid, public_state(interview, state)),
                ]
        await _broadcast(iid, msgs)
        metrics.incr("interviews_completed")
    except Exception as exc:
        log.exception("report_generation_failed")
        metrics.incr("interviews_failed")
        metrics.error("report", str(exc))
        await hub.send(iid, event("ERROR", iid, {"code": "REPORT_FAILED", "message": "We couldn't generate your report yet. Please refresh in a moment."}))


# ------------------------------------------------------------------------ actions
async def start(interview_id: uuid.UUID, user: User) -> None:
    async def fn(db: AsyncSession, iv: Interview, st: InterviewState, ctx: EngineContext) -> EngineOutput:
        if st.phase != Phase.INTERVIEW_SETUP:
            return EngineOutput()
        if not iv.consent.get("accepted"):
            raise EngineError("Consent is required before starting")
        out = await engine.start(st, ctx)
        iv.status = "in_progress"
        iv.started_at = utcnow()
        track(db, "interview_started", iv.candidate_id, iv.organization_id, iv.id)
        metrics.incr("interviews_started")
        return out

    await _run(interview_id, user, "start", fn)


async def answer(interview_id: uuid.UUID, user: User, text: str, source: str) -> None:
    async def fn(db: AsyncSession, iv: Interview, st: InterviewState, ctx: EngineContext) -> EngineOutput:
        seq = await _next_seq(db, iv.id)
        db.add(Transcript(interview_id=iv.id, speaker="candidate", kind=source, text=text, sequence=seq))
        await db.flush()
        await hub.send(str(iv.id), event("TRANSCRIPT_FINAL", iv.id, {"speaker": "candidate", "text": text, "source": source}))
        await hub.send(str(iv.id), event("AI_THINKING", iv.id, {}))
        return await engine.handle_answer(st, ctx, text)

    await _run(interview_id, user, "answer", fn)


async def end(interview_id: uuid.UUID, user: User, reason: str = "candidate") -> None:
    async def fn(db: AsyncSession, iv: Interview, st: InterviewState, ctx: EngineContext) -> EngineOutput:
        if st.phase == Phase.INTERVIEW_SETUP:
            iv.status = "abandoned"
            return EngineOutput()
        return await engine.end(st, ctx, reason)

    await _run(interview_id, user, "end", fn)


async def submit_code(interview_id: uuid.UUID, user: User, submission: CodeSubmissionSummary, statement: str) -> None:
    async def fn(db: AsyncSession, iv: Interview, st: InterviewState, ctx: EngineContext) -> EngineOutput:
        out = await engine.handle_code_submission(st, ctx, submission, statement)
        track(db, "code_submitted", iv.candidate_id, iv.organization_id, iv.id, passed=submission.passed, total=submission.total)
        return out

    await _run(interview_id, user, "submit_code", fn)


async def update_code_state(interview_id: uuid.UUID, code: str, run_result: dict[str, Any] | None = None) -> None:
    iid = str(interview_id)
    async with _locks[iid]:
        async with session_factory()() as db:
            iv = await db.get(Interview, interview_id)
            if iv is None or not iv.state:
                return
            st = InterviewState.model_validate(iv.state)
            if st.code_state is None:
                return
            st.code_state.code = code[:100_000]
            if run_result is not None:
                st.code_state.run_count += 1
                st.code_state.last_result = run_result
            iv.state = st.model_dump(mode="json")
            await db.commit()


async def check_time(interview_id: uuid.UUID) -> None:
    async def fn(db: AsyncSession, iv: Interview, st: InterviewState, ctx: EngineContext) -> EngineOutput:
        return await engine.check_time(st, ctx)

    await _run(interview_id, None, "tick", fn)


async def purge_expired() -> int:
    """Data retention: delete interviews (and their transcripts, code, snapshots, reports) older than the
    organisation's retention_days, or DATA_RETENTION_DAYS for individual candidates. Demo sessions: 7 days."""
    from datetime import timedelta

    from app.models import Organization
    from app.services.storage import get_storage

    removed = 0
    now = datetime.now(UTC)
    async with session_factory()() as db:
        orgs = {
            o.id: int((o.settings or {}).get("retention_days", get_settings().data_retention_days)) for o in (await db.execute(select(Organization))).scalars()
        }
        rows = (await db.execute(select(Interview).where(Interview.status.in_(("completed", "abandoned", "planned"))))).scalars().all()
        for iv in rows:
            days = (
                7
                if iv.is_demo
                else orgs.get(iv.organization_id, get_settings().data_retention_days)
                if iv.organization_id
                else get_settings().data_retention_days
            )
            created = iv.created_at if iv.created_at.tzinfo else iv.created_at.replace(tzinfo=UTC)
            if created < now - timedelta(days=days):
                for ev in (await db.execute(select(ScreenEvent).where(ScreenEvent.interview_id == iv.id))).scalars():
                    if ev.storage_key:
                        await get_storage().delete(ev.storage_key)
                await db.delete(iv)
                removed += 1
        await db.commit()
    if removed:
        log.info("retention_purge", extra={"removed": removed})
    return removed


async def tick_loop() -> None:
    """Background: end interviews whose time is up, even if the client went quiet; hourly retention purge."""
    last_purge = 0.0
    while True:
        await asyncio.sleep(5)
        try:
            if now_ts() - last_purge > 3600:
                last_purge = now_ts()
                await purge_expired()
            async with session_factory()() as db:
                ids = (await db.execute(select(Interview.id).where(Interview.status == "in_progress"))).scalars().all()
                due = []
                for iid in ids:
                    iv = await db.get(Interview, iid)
                    if iv and iv.state and iv.state.get("deadline_at") and iv.state["deadline_at"] < now_ts():
                        due.append(iid)
            for iid in due:
                await check_time(iid)
            # recover interviews stuck in evaluating (e.g. after a restart)
            async with session_factory()() as db:
                stuck = (await db.execute(select(Interview.id).where(Interview.status == "evaluating"))).scalars().all()
            for iid in stuck:
                if not _locks[str(iid)].locked():
                    await finalize(iid)
        except Exception as exc:  # keep the loop alive
            log.exception("tick_failed")
            metrics.error("tick", str(exc))
