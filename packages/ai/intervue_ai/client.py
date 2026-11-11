"""`AIClient` wraps a provider chain with timeouts, retries, fallback and usage callbacks."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel

from intervue_ai.base import AIProvider, AIProviderError, AIRequest, AIResult
from intervue_ai.mock_provider import MockAIProvider, has_handler

T = TypeVar("T", bound=BaseModel)
log = logging.getLogger("intervue.ai")

UsageCallback = Callable[[AIRequest[BaseModel], AIResult[BaseModel]], Awaitable[None]]
ErrorCallback = Callable[[str, str, str], None]  # (task, provider, message)


class AIClient:
    def __init__(
        self,
        providers: list[AIProvider],
        timeout_seconds: float = 60.0,
        attempts_per_provider: int = 2,
        deterministic_fallback: bool = True,
    ) -> None:
        if not providers:
            raise ValueError("At least one provider is required")
        self.providers = providers
        self.timeout_seconds = timeout_seconds
        self.attempts = attempts_per_provider
        self.deterministic_fallback = deterministic_fallback
        self._mock = MockAIProvider()
        self.on_usage: UsageCallback | None = None
        self.on_error: ErrorCallback | None = None
        self._disabled_until: dict[int, float] = {}  # circuit breaker per provider index

    @property
    def primary(self) -> AIProvider:
        return self.providers[0]

    async def run(self, request: AIRequest[T]) -> AIResult[T]:
        errors: list[str] = []
        for idx, provider in enumerate(self.providers):
            if self._disabled_until.get(idx, 0.0) > time.monotonic():
                errors.append(f"{provider.name}: temporarily disabled")
                continue
            for attempt in range(1, self.attempts + 1):
                try:
                    result = await asyncio.wait_for(provider.generate(request), self.timeout_seconds)
                    result.fallback_used = idx > 0
                    await self._report(request, result)
                    return result
                except TimeoutError:
                    errors.append(f"{provider.name}: timeout")
                except AIProviderError as exc:
                    errors.append(f"{provider.name}: {exc}")
                    if exc.cooldown_seconds > 0:
                        self._disabled_until[idx] = time.monotonic() + exc.cooldown_seconds
                        log.error("ai_provider_disabled", extra={"provider": provider.name, "model": provider.model, "reason": str(exc)})
                        if self.on_error is not None:
                            self.on_error(request.task, f"{provider.name}:{provider.model}", str(exc))
                    if not exc.retryable:
                        break
                log.warning("ai_call_failed", extra={"task": request.task, "provider": provider.name, "attempt": attempt})
                if attempt < self.attempts:
                    await asyncio.sleep(0.4 * attempt)
        if self.deterministic_fallback and has_handler(request.task) and not self.primary.is_mock:
            log.error("ai_fallback_deterministic", extra={"task": request.task, "errors": errors})
            result = await self._mock.generate(request)
            result.fallback_used = True
            await self._report(request, result)
            return result
        raise AIProviderError("; ".join(errors) or "all providers failed", retryable=False)

    async def _report(self, request: AIRequest[T], result: AIResult[T]) -> None:
        if self.on_usage is not None:
            try:
                await self.on_usage(request, result)  # type: ignore[arg-type]
            except Exception:  # metering must never break the interview
                log.exception("usage_callback_failed")
