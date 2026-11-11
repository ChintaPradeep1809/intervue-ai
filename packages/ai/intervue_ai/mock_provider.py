"""Deterministic local provider.

Each task registers a handler that computes the schema output from `request.context` using
rule-based logic (taxonomy matching, concept coverage, curated follow-ups). It makes the product
fully runnable without API keys and is also the last-resort fallback when an LLM call fails.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from intervue_ai.base import AIProvider, AIProviderError, AIRequest, AIResult, TokenUsage

T = TypeVar("T", bound=BaseModel)

Handler = Callable[[dict[str, Any]], BaseModel]

_HANDLERS: dict[str, Handler] = {}


def register_handler(task: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _HANDLERS[task] = fn
        return fn

    return deco


def has_handler(task: str) -> bool:
    return task in _HANDLERS


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class MockAIProvider(AIProvider):
    name = "mock"
    model = "rule-based-v1"
    is_mock = True

    async def generate(self, request: AIRequest[T]) -> AIResult[T]:
        started = time.perf_counter()
        handler = _HANDLERS.get(request.task)
        if handler is None:
            raise AIProviderError(f"No deterministic handler for task '{request.task}'", retryable=False)
        out = handler(request.context)
        if not isinstance(out, request.schema):
            out = request.schema.model_validate(out.model_dump())
        # Token counts are estimates so the cost pipeline is exercised end-to-end (priced at $0).
        usage = TokenUsage(
            input_tokens=_approx_tokens(request.system + request.prompt),
            output_tokens=_approx_tokens(out.model_dump_json()),
        )
        return AIResult(
            output=out,
            provider=self.name,
            model=self.model,
            usage=usage,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
