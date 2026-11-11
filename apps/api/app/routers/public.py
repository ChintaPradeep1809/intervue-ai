"""Unauthenticated endpoints: catalog, public config, health, demo mode."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Request, Response
from sqlalchemy import select, text

from app.config import get_settings
from app.db import session_factory
from app.deps import DB, client_ip
from app.models import CandidateProfile, Plan, User
from app.routers.auth import set_session_cookie
from app.routers.interviews import interview_detail
from app.services.ai import get_ai_client, get_voice_provider, provider_summary
from app.services.audit import audit
from app.services.interviews import create_interview
from intervue_engine import INTERVIEW_TYPES, ROLES, TOPICS

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/config")
async def public_config() -> dict[str, Any]:
    s = get_settings()
    return {
        "brand_name": s.brand_name,
        "google_oauth": bool(s.google_client_id),
        "demo_enabled": s.demo_enabled,
        "demo_duration_minutes": s.demo_duration_minutes,
        "ai_is_mock": get_ai_client().primary.is_mock,
        "voice": get_voice_provider().session_config().__dict__,
        "environment": s.environment,
    }


@router.get("/catalog")
async def catalog() -> dict[str, Any]:
    return {
        "roles": [
            {
                "key": r.key,
                "title": r.title,
                "description": r.description,
                "topics": list(r.topic_weights),
                "has_sql_round": r.has_sql_round,
                "coding_language": r.coding_language,
            }
            for r in ROLES.values()
        ],
        "topics": [{"key": t.key, "label": t.label} for t in TOPICS.values()],
        "interview_types": INTERVIEW_TYPES,
        "durations": [30, 45, 60],
        "difficulties": ["easy", "medium", "hard"],
        "round_kinds": ["introduction", "technical", "coding", "sql", "system_design", "behavioral"],
        "languages": ["python", "javascript", "typescript", "sql"],
    }


@router.get("/plans")
async def plans(db: DB) -> dict[str, Any]:
    rows = (await db.execute(select(Plan).where(Plan.is_public.is_(True)).order_by(Plan.sort_order))).scalars().all()
    return {
        "items": [
            {
                "key": p.key,
                "name": p.name,
                "audience": p.audience,
                "price_monthly_usd": p.price_monthly_usd,
                "price_monthly_inr": p.price_monthly_inr,
                "limits": p.limits,
                "features": p.features,
            }
            for p in rows
        ]
    }


_voice_preview: dict[str, dict[str, str]] = {}
VOICE_PREVIEW_TEXT = "Hi, I'm your interviewer. If you can hear me clearly, you're all set."


@router.get("/voice/preview")
async def voice_preview() -> dict[str, Any]:
    """Sample of the configured interviewer voice for the setup check. Fixed text, cached per voice."""
    vp = get_voice_provider()
    cfg = vp.session_config()
    if cfg.tts != "server":
        return {"tts": cfg.tts, "text": VOICE_PREVIEW_TEXT, "language": cfg.language, "audio": None}
    key = f"{vp.name}:{cfg.voice_hint}"
    if key not in _voice_preview:
        try:
            audio = await vp.synthesize(VOICE_PREVIEW_TEXT)
        except Exception:
            return {"tts": "browser", "text": VOICE_PREVIEW_TEXT, "language": cfg.language, "audio": None, "error": "Server voice unavailable"}
        if audio is None:
            return {"tts": "browser", "text": VOICE_PREVIEW_TEXT, "language": cfg.language, "audio": None}
        _voice_preview[key] = {"mime_type": audio.mime_type, "b64": audio.audio_b64}
    return {"tts": "server", "text": VOICE_PREVIEW_TEXT, "language": cfg.language, "audio": _voice_preview[key]}


@router.get("/health")
async def health() -> dict[str, Any]:
    db_ok = True
    try:
        async with session_factory()() as db:
            await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "providers": provider_summary()}


@router.post("/demo/start")
async def start_demo(request: Request, response: Response, db: DB) -> dict[str, Any]:
    s = get_settings()
    if not s.demo_enabled:
        response.status_code = 404
        return {"detail": "Demo mode is disabled."}
    user = User(email=f"demo-{secrets.token_hex(6)}@demo.intervue.local", full_name="Demo Candidate", is_demo=True)
    db.add(user)
    await db.flush()
    db.add(CandidateProfile(user_id=user.id, experience_years=2, target_role="aws_data_engineer", onboarding_completed=True))
    template_rounds = [
        {"kind": "introduction", "title": "Introduction", "minutes": 1, "topics": ["introduction"]},
        {"kind": "technical", "title": "SQL & PySpark", "minutes": 4, "topics": ["sql", "pyspark", "aws"], "question_count": 2},
        {"kind": "behavioral", "title": "Behavioral", "minutes": 2, "topics": ["behavioral"]},
    ]
    from app.models import InterviewTemplate

    tmpl = InterviewTemplate(
        name="Demo",
        role_key="aws_data_engineer",
        duration_minutes=s.demo_duration_minutes,
        rounds=template_rounds,
        jd_text="AWS Data Engineer, 2 years: SQL, Python, PySpark, AWS Glue, Athena, S3, Redshift, Airflow.",
    )
    iv = await create_interview(
        db,
        user,
        role_key="aws_data_engineer",
        interview_type="full",
        duration_minutes=s.demo_duration_minutes,
        difficulty="medium",
        template=tmpl,
        is_demo=True,
        title="AWS Data Engineer — Demo interview",
    )
    audit(db, "demo.start", user.id, ip=client_ip(request))
    await db.commit()
    set_session_cookie(response, user)
    return interview_detail(iv)
