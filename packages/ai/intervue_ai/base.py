"""Provider-neutral AI interfaces.

Every AI call in the product is a *task* with a Pydantic output schema. Providers never return
free-form text to application code: output is validated against the schema or the call fails.
"""

from __future__ import annotations

import abc
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

Effort = Literal["low", "medium", "high"]


class AIProviderError(Exception):
    """Raised when a provider cannot produce a valid result (after its own retries)."""

    def __init__(self, message: str, *, retryable: bool = True, cooldown_seconds: float = 0.0) -> None:
        super().__init__(message)
        self.retryable = retryable
        # > 0: the provider is unusable for a while (no credits, bad key); skip it instead of retrying
        self.cooldown_seconds = cooldown_seconds


@dataclass
class ImageInput:
    media_type: str  # image/jpeg | image/png | image/webp
    data_b64: str


@dataclass
class ToolSpec:
    """A read-only tool the model may call before answering."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[str]]


@dataclass
class AIRequest(Generic[T]):
    task: str
    schema: type[T]
    system: str
    prompt: str
    # Structured inputs. Deterministic providers compute from these; LLM providers see `prompt`.
    context: dict[str, Any] = field(default_factory=dict)
    images: list[ImageInput] = field(default_factory=list)
    tools: list[ToolSpec] = field(default_factory=list)
    effort: Effort = "low"
    max_tokens: int = 4000


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0

    def add(self, other: TokenUsage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens


@dataclass
class AIResult(Generic[T]):
    output: T
    provider: str
    model: str
    usage: TokenUsage
    latency_ms: int
    fallback_used: bool = False
    tool_calls: list[str] = field(default_factory=list)


class AIProvider(abc.ABC):
    name: str
    model: str
    is_mock: bool = False

    @abc.abstractmethod
    async def generate(self, request: AIRequest[T]) -> AIResult[T]: ...


class EmbeddingProvider(abc.ABC):
    name: str
    model: str
    dimensions: int

    @abc.abstractmethod
    async def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        """Return (vectors, tokens_used)."""
