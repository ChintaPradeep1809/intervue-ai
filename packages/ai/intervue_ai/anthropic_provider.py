"""Claude provider (Anthropic Messages API) with structured outputs and a bounded tool loop."""

from __future__ import annotations

import json
import time
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from intervue_ai.base import AIProvider, AIProviderError, AIRequest, AIResult, TokenUsage
from intervue_ai.schema import to_strict_json_schema

T = TypeVar("T", bound=BaseModel)

MAX_TOOL_ROUNDS = 3
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(
        self,
        api_key: str | None,
        model: str,
        timeout_seconds: float = 45.0,
        max_retries: int = 2,
        server_fallbacks: bool = True,
    ) -> None:
        self.model = model
        self._server_fallbacks = server_fallbacks
        self._client = anthropic.AsyncAnthropic(api_key=api_key or None, timeout=timeout_seconds, max_retries=max_retries)

    async def generate(self, request: AIRequest[T]) -> AIResult[T]:
        started = time.perf_counter()
        usage = TokenUsage()
        schema = to_strict_json_schema(request.schema)
        tools = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in request.tools
        ]
        handlers = {t.name: t.handler for t in request.tools}

        content: list[dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": i.media_type, "data": i.data_b64}} for i in request.images
        ]
        content.append({"type": "text", "text": request.prompt})
        messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
        tool_calls: list[str] = []

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "system": [{"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}],
            "output_config": {
                "effort": request.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        }
        if self._server_fallbacks:
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"

        for round_no in range(MAX_TOOL_ROUNDS + 1):
            call_kwargs = dict(kwargs, messages=messages)
            if tools and round_no < MAX_TOOL_ROUNDS:
                call_kwargs["tools"] = tools
            try:
                response = await self._client.beta.messages.create(**call_kwargs)
            except anthropic.AuthenticationError as exc:
                raise AIProviderError("Anthropic authentication failed - check AI_API_KEY", retryable=False, cooldown_seconds=300) from exc
            except anthropic.BadRequestError as exc:
                if "credit" in exc.message.lower():
                    raise AIProviderError("Anthropic account has no credits", retryable=False, cooldown_seconds=300) from exc
                raise AIProviderError(f"Anthropic rejected request: {exc.message}", retryable=False) from exc
            except anthropic.RateLimitError as exc:
                raise AIProviderError("Anthropic rate limited") from exc
            except anthropic.APIStatusError as exc:
                raise AIProviderError(f"Anthropic API error {exc.status_code}") from exc
            except anthropic.APIConnectionError as exc:  # includes timeouts
                raise AIProviderError("Anthropic connection error") from exc

            u = response.usage
            usage.add(
                TokenUsage(
                    input_tokens=u.input_tokens or 0,
                    output_tokens=u.output_tokens or 0,
                    cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                )
            )

            if response.stop_reason == "refusal":
                raise AIProviderError("Model declined the request", retryable=False)
            if response.stop_reason == "max_tokens":
                raise AIProviderError("Model output truncated (max_tokens)")

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason == "tool_use" and tool_uses:
                messages.append({"role": "assistant", "content": response.content})
                results = []
                for block in tool_uses:
                    tool_calls.append(block.name)
                    handler = handlers.get(block.name)
                    if handler is None:
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": "Unknown tool", "is_error": True})
                        continue
                    try:
                        out = await handler(dict(block.input))
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": out})
                    except Exception as exc:  # tool failures are reported to the model, not raised
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": f"Tool error: {exc}", "is_error": True})
                messages.append({"role": "user", "content": results})
                continue

            text = next((b.text for b in response.content if b.type == "text"), None)
            if text is None:
                raise AIProviderError("No text block in response")
            try:
                parsed = request.schema.model_validate(json.loads(text))
            except (json.JSONDecodeError, ValidationError) as exc:
                raise AIProviderError(f"Schema validation failed: {exc}") from exc
            return AIResult(
                output=parsed,
                provider=self.name,
                model=getattr(response, "model", self.model),
                usage=usage,
                latency_ms=int((time.perf_counter() - started) * 1000),
                tool_calls=tool_calls,
            )
        raise AIProviderError("Tool loop exceeded limit")
