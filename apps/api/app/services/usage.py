"""Usage metering and per-interview cost records.

AI calls happen deep inside the engine; instead of threading a DB session through it, usage is
collected into a context-local buffer and flushed by the caller inside its own transaction.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AppSetting, CostRecord, Interview, UsageRecord
from app.services.metrics import metrics
from intervue_ai import AIRequest, AIResult, PricingConfig, load_pricing


@dataclass
class UsageScope:
    user_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    interview_id: uuid.UUID | None = None
    records: list[UsageRecord] = field(default_factory=list)


_scope: ContextVar[UsageScope | None] = ContextVar("usage_scope", default=None)
_pricing_cache: dict[str, Any] = {}


@contextmanager
def usage_scope(user_id: uuid.UUID | None, organization_id: uuid.UUID | None, interview_id: uuid.UUID | None) -> Iterator[UsageScope]:
    scope = UsageScope(user_id, organization_id, interview_id)
    token = _scope.set(scope)
    try:
        yield scope
    finally:
        _scope.reset(token)


def pricing() -> PricingConfig:
    p = _pricing_cache.get("pricing")
    if p is None:
        p = load_pricing(get_settings().pricing_config_path, _pricing_cache.get("overrides"))
        _pricing_cache["pricing"] = p
    return p  # type: ignore[no-any-return]


async def load_pricing_overrides(db: AsyncSession) -> None:
    row = await db.get(AppSetting, "pricing")
    _pricing_cache.pop("pricing", None)
    _pricing_cache["overrides"] = row.value if row else None


def fx_rate() -> float:
    return float(_pricing_cache.get("fx_rate") or get_settings().usd_inr_rate)


async def load_fx_override(db: AsyncSession) -> None:
    row = await db.get(AppSetting, "fx")
    _pricing_cache["fx_rate"] = row.value.get("usd_inr") if row else None


async def on_ai_usage(request: AIRequest[Any], result: AIResult[Any]) -> None:
    metrics.observe(f"ai:{request.task}", result.latency_ms)
    metrics.incr("ai_calls")
    if result.fallback_used:
        metrics.incr("ai_fallbacks")
    scope = _scope.get()
    if scope is None:
        return
    in_cost, out_cost = pricing().llm_cost(result.provider, result.model, result.usage.input_tokens, result.usage.output_tokens, result.usage.cache_read_tokens)
    scope.records.append(
        UsageRecord(
            organization_id=scope.organization_id,
            user_id=scope.user_id,
            interview_id=scope.interview_id,
            kind="llm",
            provider=result.provider,
            model=result.model,
            task=request.task,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cache_read_tokens=result.usage.cache_read_tokens,
            cost_usd=in_cost + out_cost,
            latency_ms=result.latency_ms,
            fallback_used=result.fallback_used,
        )
    )


def record(kind: str, provider: str, quantity: float, cost_usd: float, task: str = "", latency_ms: int = 0, tokens: int = 0) -> None:
    scope = _scope.get()
    if scope is None:
        return
    scope.records.append(
        UsageRecord(
            organization_id=scope.organization_id,
            user_id=scope.user_id,
            interview_id=scope.interview_id,
            kind=kind,
            provider=provider,
            task=task,
            quantity=quantity,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            input_tokens=tokens,
        )
    )


def flush(db: AsyncSession, scope: UsageScope) -> None:
    for r in scope.records:
        db.add(r)
    scope.records.clear()


async def recompute_cost(db: AsyncSession, interview: Interview) -> CostRecord:
    rows = (
        await db.execute(
            select(
                UsageRecord.kind,
                func.sum(UsageRecord.input_tokens),
                func.sum(UsageRecord.output_tokens),
                func.sum(UsageRecord.quantity),
                func.sum(UsageRecord.cost_usd),
            )
            .where(UsageRecord.interview_id == interview.id)
            .group_by(UsageRecord.kind)
        )
    ).all()
    agg = {k: (int(i or 0), int(o or 0), float(q or 0), float(c or 0)) for k, i, o, q, c in rows}
    # split LLM cost into input/output using per-record pricing
    llm_rows = (
        await db.execute(
            select(UsageRecord.provider, UsageRecord.model, UsageRecord.input_tokens, UsageRecord.output_tokens, UsageRecord.cache_read_tokens).where(
                UsageRecord.interview_id == interview.id, UsageRecord.kind == "llm"
            )
        )
    ).all()
    p = pricing()
    llm_in = llm_out = 0.0
    for prov, model, i, o, c in llm_rows:
        a, b = p.llm_cost(prov, model, i, o, c)
        llm_in += a
        llm_out += b
    cr = (await db.execute(select(CostRecord).where(CostRecord.interview_id == interview.id))).scalar_one_or_none()
    if cr is None:
        cr = CostRecord(interview_id=interview.id, organization_id=interview.organization_id)
        db.add(cr)
    duration = 0
    if interview.started_at and interview.completed_at:
        duration = int((interview.completed_at - interview.started_at).total_seconds())
    cr.duration_seconds = duration
    cr.llm_input_tokens = agg.get("llm", (0, 0, 0, 0))[0]
    cr.llm_output_tokens = agg.get("llm", (0, 0, 0, 0))[1]
    cr.voice_seconds = agg.get("voice", (0, 0, 0, 0))[2]
    cr.embedding_tokens = agg.get("embedding", (0, 0, 0, 0))[0]
    cr.code_execution_seconds = agg.get("execution", (0, 0, 0, 0))[2]
    cr.storage_bytes = int(agg.get("storage", (0, 0, 0, 0))[2])
    cr.llm_input_cost = llm_in
    cr.llm_output_cost = llm_out
    cr.voice_cost = agg.get("voice", (0, 0, 0, 0))[3] + agg.get("tts", (0, 0, 0, 0))[3]
    cr.embedding_cost = agg.get("embedding", (0, 0, 0, 0))[3]
    cr.execution_cost = agg.get("execution", (0, 0, 0, 0))[3]
    cr.storage_cost = agg.get("storage", (0, 0, 0, 0))[3]
    cr.estimated_cost_usd = round(llm_in + llm_out + cr.voice_cost + cr.embedding_cost + cr.execution_cost + cr.storage_cost, 6)
    cr.fx_rate = fx_rate()
    cr.estimated_cost_inr = round(cr.estimated_cost_usd * cr.fx_rate, 4)
    return cr


def pricing_json() -> str:
    return json.dumps(pricing().model_dump(), indent=2)
