"""OpenAI provider on the Responses API: strict structured outputs, reasoning effort and a bounded
function-tool loop. (Chat Completions rejects function tools with reasoning effort on current
reasoning models, so the Responses API is used throughout.)"""

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


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str | None, model: str, timeout_seconds: float = 45.0, max_retries: int = 2) -> None:
        self.model = model
        # AIClient owns retries/fallback; keep SDK retries low so a failing call doesn't stall a live turn.
        self._client = openai.AsyncOpenAI(api_key=api_key or None, timeout=openai.Timeout(timeout_seconds, connect=5.0), max_retries=min(max_retries, 1))
        # Some models don't accept a reasoning effort; remember that instead of failing every call.
        self._supports_effort = True

    async def generate(self, request: AIRequest[T]) -> AIResult[T]:
        started = time.perf_counter()
        usage = TokenUsage()
        schema_name = re.sub(r"[^a-zA-Z0-9_-]", "_", request.task)[:64] or "output"
        text_format = {"format": {"type": "json_schema", "name": schema_name, "schema": to_strict_json_schema(request.schema), "strict": True}}
        tools = [{"type": "function", "name": t.name, "description": t.description, "parameters": t.input_schema, "strict": True} for t in request.tools]
        handlers = {t.name: t.handler for t in request.tools}

        content: list[dict[str, Any]] = [{"type": "input_text", "text": request.prompt}]
        content += [{"type": "input_image", "image_url": f"data:{i.media_type};base64,{i.data_b64}"} for i in request.images]
        items: list[Any] = [{"role": "user", "content": content}]
        tool_calls_made: list[str] = []

        for round_no in range(MAX_TOOL_ROUNDS + 1):
            kwargs: dict[str, Any] = {
                "model": self.model,
                "instructions": request.system,
                "input": items,
                "text": text_format,
                "max_output_tokens": request.max_tokens,
                "prompt_cache_key": f"intervue-{schema_name}",
                "store": False,
            }
            if self._supports_effort:
                kwargs["reasoning"] = {"effort": request.effort}
                # replay reasoning between tool rounds without server-side storage
                kwargs["include"] = ["reasoning.encrypted_content"]
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto" if round_no < MAX_TOOL_ROUNDS else "none"
            response = await self._call(kwargs)

            u = response.usage
            if u is not None:
                details = getattr(u, "input_tokens_details", None)
                usage.add(
                    TokenUsage(
                        input_tokens=u.input_tokens or 0,
                        output_tokens=u.output_tokens or 0,
                        cache_read_tokens=(getattr(details, "cached_tokens", 0) or 0) if details else 0,
                    )
                )
            if response.status == "incomplete":
                reason = getattr(response.incomplete_details, "reason", "unknown")
                raise AIProviderError(f"Model output incomplete ({reason})", retryable=reason != "content_filter")

            outputs = list(response.output or [])
            for item in outputs:
                if item.type == "message":
                    for part in item.content or []:
                        if part.type == "refusal":
                            raise AIProviderError("Model declined the request", retryable=False)

            calls = [o for o in outputs if o.type == "function_call"]
            if calls:
                items += [o.model_dump(exclude_none=True) for o in outputs]
                for call in calls:
                    tool_calls_made.append(call.name)
                    handler = handlers.get(call.name)
                    try:
                        args = json.loads(call.arguments or "{}")
                        result = await handler(args) if handler else "Unknown tool"
                    except Exception as exc:  # tool failures go back to the model, they don't abort the call
                        result = f"Tool error: {exc}"
                    items.append({"type": "function_call_output", "call_id": call.call_id, "output": result})
                continue

            text = response.output_text
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
        try:
            return await self._client.responses.create(**kwargs)
        except openai.BadRequestError as exc:
            if "reasoning" in kwargs and "reasoning" in str(exc).lower():
                kwargs.pop("reasoning")
                kwargs.pop("include", None)
                result = await self._call(kwargs)
                self._supports_effort = False
                return result
            raise AIProviderError(f"OpenAI rejected request: {exc.message}", retryable=False) from exc
        except openai.AuthenticationError as exc:
            raise AIProviderError("OpenAI authentication failed - check AI_API_KEY", retryable=False, cooldown_seconds=300) from exc
        except openai.RateLimitError as exc:
            body = exc.body if isinstance(exc.body, dict) else {}
            code = str(body.get("code") or body.get("type") or "")
            if code in ("insufficient_quota", "credit_balance_exhausted", "billing_hard_limit_reached"):
                raise AIProviderError(
                    "OpenAI account has no credits - add credits at platform.openai.com billing", retryable=False, cooldown_seconds=300
                ) from exc
            raise AIProviderError("OpenAI rate limited") from exc
        except openai.APIStatusError as exc:
            raise AIProviderError(f"OpenAI API error {exc.status_code}") from exc
        except openai.APITimeoutError as exc:
            raise AIProviderError("OpenAI request timed out") from exc
        except openai.APIConnectionError as exc:
            # network down / DNS failure: skip this model briefly so turns fall through immediately
            raise AIProviderError("OpenAI connection error", retryable=False, cooldown_seconds=30) from exc
