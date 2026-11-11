"""Provider for OpenAI-compatible Chat Completions endpoints: Google Gemini (free tier), Groq,
OpenRouter, Ollama and similar. Strict JSON-schema structured outputs and a bounded function-tool
loop, like the other providers."""

from __future__ import annotations

import json
import re
import time
from typing import Any, TypeVar

import openai
from pydantic import BaseModel, ValidationError

from intervue_ai.base import AIProvider, AIProviderError, AIRequest, AIResult, TokenUsage
from intervue_ai.schema import to_strict_json_schema

T = TypeVar("T", bound=BaseModel)

MAX_TOOL_ROUNDS = 3
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


class ChatCompletionsProvider(AIProvider):
    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str,
        name: str = "openai_compat",
        timeout_seconds: float = 45.0,
        max_retries: int = 2,
    ) -> None:
        self.name = name
        self.model = model
        # AIClient owns retries/fallback; keep SDK retries low so a failing call doesn't stall a live turn.
        self._client = openai.AsyncOpenAI(
            api_key=api_key or "not-needed",
            base_url=base_url,
            timeout=openai.Timeout(timeout_seconds, connect=5.0),
            max_retries=min(max_retries, 1),
        )
        self._supports_effort = True

    async def generate(self, request: AIRequest[T]) -> AIResult[T]:
        started = time.perf_counter()
        usage = TokenUsage()
        schema_name = re.sub(r"[^a-zA-Z0-9_-]", "_", request.task)[:64] or "output"
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": to_strict_json_schema(request.schema), "strict": True},
        }
        tools = [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.input_schema, "strict": True},
            }
            for t in request.tools
        ]
        handlers = {t.name: t.handler for t in request.tools}

        user: Any = request.prompt
        if request.images:
            user = [{"type": "text", "text": request.prompt}] + [
                {"type": "image_url", "image_url": {"url": f"data:{i.media_type};base64,{i.data_b64}"}} for i in request.images
            ]
        messages: list[dict[str, Any]] = [{"role": "system", "content": request.system}, {"role": "user", "content": user}]
        tool_calls_made: list[str] = []

        for round_no in range(MAX_TOOL_ROUNDS + 1):
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "response_format": response_format,
                "max_completion_tokens": request.max_tokens,
            }
            if self._supports_effort:
                kwargs["reasoning_effort"] = request.effort
            if tools and round_no < MAX_TOOL_ROUNDS:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            response = await self._call(kwargs)

            u = response.usage
            if u is not None:
                details = getattr(u, "prompt_tokens_details", None)
                usage.add(
                    TokenUsage(
                        input_tokens=u.prompt_tokens or 0,
                        output_tokens=u.completion_tokens or 0,
                        cache_read_tokens=(getattr(details, "cached_tokens", 0) or 0) if details else 0,
                    )
                )
            if not response.choices:
                raise AIProviderError("Empty response")
            choice = response.choices[0]
            message = choice.message
            if getattr(message, "refusal", None):
                raise AIProviderError("Model declined the request", retryable=False)

            if message.tool_calls:
                # keep provider extras (e.g. Gemini thought signatures) when replaying the assistant turn
                messages.append(message.model_dump(exclude_none=True))
                for call in message.tool_calls:
                    name = call.function.name
                    tool_calls_made.append(name)
                    handler = handlers.get(name)
                    try:
                        args = json.loads(call.function.arguments or "{}")
                        result = await handler(args) if handler else "Unknown tool"
                    except Exception as exc:  # tool failures go back to the model, they don't abort the call
                        result = f"Tool error: {exc}"
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
                continue

            if choice.finish_reason == "length":
                raise AIProviderError("Model output incomplete (max_tokens)")
            if choice.finish_reason == "content_filter":
                raise AIProviderError("Model output blocked by content filter", retryable=False)
            text = _FENCE.sub("", (message.content or "").strip())
            if not text:
                raise AIProviderError("Empty response")
            try:
                parsed = request.schema.model_validate(json.loads(text))
            except (json.JSONDecodeError, ValidationError) as exc:
                raise AIProviderError(f"Schema validation failed: {exc}") from exc
            return AIResult(
                output=parsed,
                provider=self.name,
                model=response.model or self.model,
                usage=usage,
                latency_ms=int((time.perf_counter() - started) * 1000),
                tool_calls=tool_calls_made,
            )
        raise AIProviderError("Tool loop exceeded limit")

    async def _call(self, kwargs: dict[str, Any]) -> Any:
        label = self.name.capitalize()
        try:
            return await self._client.chat.completions.create(**kwargs)
        except openai.BadRequestError as exc:
            if "reasoning_effort" in kwargs and "reason" in str(exc).lower():
                kwargs.pop("reasoning_effort")
                result = await self._call(kwargs)
                self._supports_effort = False
                return result
            raise AIProviderError(f"{label} rejected request: {exc.message}", retryable=False) from exc
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise AIProviderError(f"{label} authentication failed - check AI_API_KEY", retryable=False, cooldown_seconds=300) from exc
        except openai.NotFoundError as exc:
            raise AIProviderError(f"{label} model '{self.model}' not available", retryable=False, cooldown_seconds=600) from exc
        except openai.RateLimitError as exc:
            text = str(exc).lower()
            if "per day" in text or "perday" in text or "insufficient_quota" in text or "credit" in text:
                raise AIProviderError(f"{label} daily quota exhausted", retryable=False, cooldown_seconds=3600) from exc
            # free tiers have low per-minute limits: step aside for a minute and let the next model answer
            raise AIProviderError(f"{label} rate limited", retryable=False, cooldown_seconds=60) from exc
        except openai.APIStatusError as exc:
            if exc.status_code == 503:  # free-tier demand spikes are brief: AIClient retries once, then the next model
                raise AIProviderError(f"{label} model overloaded") from exc
            raise AIProviderError(f"{label} API error {exc.status_code}") from exc
        except openai.APITimeoutError as exc:
            raise AIProviderError(f"{label} request timed out") from exc
        except openai.APIConnectionError as exc:
            # network down / DNS failure: skip this model briefly so turns fall through immediately
            raise AIProviderError(f"{label} connection error", retryable=False, cooldown_seconds=30) from exc
