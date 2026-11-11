"""Interview WebSocket. Auth via a short-lived ticket from POST /api/interviews/{id}/ws-ticket."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.db import session_factory
from app.models import Interview, User
from app.services import orchestrator
from app.services.audit import track
from app.services.metrics import metrics
from app.services.usage import flush, pricing, record, usage_scope
from intervue_engine import EngineError, InterviewState
from intervue_security import RateLimiter, TokenError, decode_token

router = APIRouter()
log = logging.getLogger("intervue.ws")
_ws_limiter = RateLimiter()
MAX_ANSWER_CHARS = 8000


@router.websocket("/ws/interviews/{interview_id}")
async def interview_ws(websocket: WebSocket, interview_id: uuid.UUID) -> None:
    ticket = websocket.query_params.get("ticket", "")
    try:
        payload = decode_token(get_settings().auth_secret, ticket, "ws")
        if payload.get("iid") != str(interview_id):
            raise TokenError("wrong interview")
    except TokenError:
        await websocket.close(code=4401)
        return
    async with session_factory()() as db:
        user = await db.get(User, uuid.UUID(payload["sub"]))
        interview = await db.get(Interview, interview_id)
        if user is None or interview is None or interview.candidate_id != user.id:
            await websocket.close(code=4403)
            return
        state = InterviewState.model_validate(interview.state) if interview.state else None
        initial = orchestrator.public_state(interview, state)
    await websocket.accept()
    iid = str(interview_id)
    orchestrator.hub.add(iid, websocket)
    metrics.incr("ws_connections")
    await websocket.send_text(json.dumps(orchestrator.event("STATE_SYNC", iid, {**initial, "resumed": bool(state and state.started_at)}), default=str))
    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw) > 200_000:
                await websocket.send_text(json.dumps(orchestrator.event("ERROR", iid, {"code": "TOO_LARGE", "message": "Message too large."})))
                continue
            ok, _ = _ws_limiter.hit(f"{iid}", 120, 60)
            if not ok:
                await websocket.send_text(json.dumps(orchestrator.event("ERROR", iid, {"code": "RATE_LIMITED", "message": "Slow down a little."})))
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await _handle(websocket, iid, interview_id, user, msg)
    except WebSocketDisconnect:
        pass
    finally:
        orchestrator.hub.remove(iid, websocket)


async def _handle(ws: WebSocket, iid: str, interview_id: uuid.UUID, user: User, msg: dict) -> None:  # type: ignore[type-arg]
    mtype = msg.get("type")
    try:
        if mtype == "PING":
            await ws.send_text(json.dumps(orchestrator.event("PONG", iid, {"server_time": orchestrator.now_ts()})))
        elif mtype == "START":
            await orchestrator.start(interview_id, user)
        elif mtype == "ANSWER":
            text = str(msg.get("text", "")).strip()[:MAX_ANSWER_CHARS]
            if not text:
                return
            await orchestrator.answer(interview_id, user, text, "typed" if msg.get("source") == "typed" else "voice")
        elif mtype == "TRANSCRIPT_PARTIAL":
            await orchestrator.hub.send(iid, orchestrator.event("TRANSCRIPT_PARTIAL", iid, {"text": str(msg.get("text", ""))[:2000]}))
        elif mtype in ("CANDIDATE_SPEAKING", "AI_SPEAKING_DONE"):
            pass  # presence signals; nothing to persist
        elif mtype == "CODE_CHANGED":
            await orchestrator.update_code_state(interview_id, str(msg.get("code", ""))[:100_000])
        elif mtype == "END":
            await orchestrator.end(interview_id, user, "candidate")
        elif mtype == "REQUEST_STATE":
            async with session_factory()() as db:
                iv = await db.get(Interview, interview_id)
                st = InterviewState.model_validate(iv.state) if iv and iv.state else None
                await ws.send_text(json.dumps(orchestrator.event("STATE_SYNC", iid, orchestrator.public_state(iv, st)), default=str))  # type: ignore[arg-type]
        elif mtype == "VOICE_SESSION_STARTED":
            async with session_factory()() as db:
                iv = await db.get(Interview, interview_id)
                track(db, "voice_session_started", user.id, iv.organization_id if iv else None, interview_id, provider=msg.get("provider", "browser"))
                await db.commit()
        elif mtype == "VOICE_USAGE":
            seconds = max(0.0, min(float(msg.get("stt_seconds", 0)), 4 * 3600))
            latency = int(msg.get("avg_latency_ms", 0) or 0)
            if latency:
                metrics.observe("voice:stt", latency)
            async with session_factory()() as db:
                iv = await db.get(Interview, interview_id)
                provider = str(msg.get("provider", "browser"))[:30]
                with usage_scope(user.id, iv.organization_id if iv else None, interview_id) as scope:
                    record("voice", provider, seconds, pricing().voice_cost(provider, seconds), task="stt", latency_ms=latency)
                    flush(db, scope)
                await db.commit()
    except EngineError as exc:
        await ws.send_text(json.dumps(orchestrator.event("ERROR", iid, {"code": "INVALID_ACTION", "message": str(exc)})))
    except Exception as exc:
        log.exception("ws_handler_failed")
        metrics.error("ws", str(exc))
        await ws.send_text(
            json.dumps(
                orchestrator.event(
                    "ERROR",
                    iid,
                    {
                        "code": "AI_UNAVAILABLE",
                        "message": "The interviewer hit a problem processing that. Please try again.",
                    },
                )
            )
        )
