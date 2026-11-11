"""AI provider abstraction: structured generation, embeddings, pricing."""

from intervue_ai.base import (
    AIProvider,
    AIProviderError,
    AIRequest,
    AIResult,
    EmbeddingProvider,
    ImageInput,
    TokenUsage,
    ToolSpec,
)
from intervue_ai.client import AIClient
from intervue_ai.embeddings import HashingEmbeddingProvider, cosine
from intervue_ai.mock_provider import MockAIProvider, register_handler
from intervue_ai.pricing import ModelPrice, PricingConfig, load_pricing


def build_provider(name: str, api_key: str | None, model: str, timeout_seconds: float = 45.0, base_url: str | None = None) -> AIProvider:
    if name == "mock":
        return MockAIProvider()
    if name == "anthropic":
        from intervue_ai.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=api_key, model=model, timeout_seconds=timeout_seconds)
    if name == "openai":
        from intervue_ai.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=api_key, model=model, timeout_seconds=timeout_seconds)
    if name in ("gemini", "openai_compat"):
        from intervue_ai.chat_provider import GEMINI_BASE_URL, ChatCompletionsProvider

        url = base_url or (GEMINI_BASE_URL if name == "gemini" else None)
        if not url:
            raise ValueError("AI_BASE_URL is required for AI_PROVIDER=openai_compat")
        return ChatCompletionsProvider(api_key=api_key, model=model, base_url=url, name=name, timeout_seconds=timeout_seconds)
    raise ValueError(f"Unknown AI provider '{name}'")


__all__ = [
    "AIClient",
    "AIProvider",
    "AIProviderError",
    "AIRequest",
    "AIResult",
    "EmbeddingProvider",
    "HashingEmbeddingProvider",
    "ImageInput",
    "MockAIProvider",
    "ModelPrice",
    "PricingConfig",
    "TokenUsage",
    "ToolSpec",
    "build_provider",
    "cosine",
    "load_pricing",
    "register_handler",
]
