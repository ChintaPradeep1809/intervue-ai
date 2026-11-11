"""Factory for the configured AI client, embedding provider and voice provider."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.services.metrics import metrics
from app.services.usage import on_ai_usage
from intervue_ai import AIClient, AIProvider, EmbeddingProvider, HashingEmbeddingProvider, build_provider
from intervue_voice import VoiceProvider, build_voice_provider


def _provider(model: str) -> AIProvider:
    s = get_settings()
    return build_provider(s.ai_provider, s.ai_api_key, model, s.ai_timeout_seconds, s.ai_base_url or None)


def _fallback_models() -> list[str]:
    """AI_FALLBACK_MODEL may list several models (comma-separated); free tiers meter quota per model."""
    s = get_settings()
    return [m.strip() for m in s.ai_fallback_model.split(",") if m.strip()]


def _on_ai_error(task: str, provider: str, message: str) -> None:
    metrics.error("ai", f"{provider} paused ({task}): {message}")


@lru_cache
def get_ai_client() -> AIClient:
    s = get_settings()
    providers: list[AIProvider] = [_provider(s.ai_model)]
    if s.ai_provider != "mock":
        providers += [_provider(m) for m in _fallback_models() if m != s.ai_model]
    client = AIClient(providers, timeout_seconds=s.ai_timeout_seconds + 5)
    client.on_usage = on_ai_usage
    client.on_error = _on_ai_error
    return client


@lru_cache
def get_fast_ai_client() -> AIClient:
    """Client for live interview turns. Falls back to the main model, then to the deterministic engine."""
    s = get_settings()
    if s.ai_provider == "mock" or not s.ai_fast_model or s.ai_fast_model == s.ai_model:
        return get_ai_client()
    chain = [s.ai_fast_model, s.ai_model, *_fallback_models()]
    providers: list[AIProvider] = [_provider(m) for m in dict.fromkeys(chain)]
    client = AIClient(providers, timeout_seconds=s.ai_timeout_seconds + 5)
    client.on_usage = on_ai_usage
    client.on_error = _on_ai_error
    return client


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    return HashingEmbeddingProvider()


@lru_cache
def get_voice_provider() -> VoiceProvider:
    s = get_settings()
    return build_voice_provider(s.voice_provider, s.voice_api_key, s.voice_id)


def provider_summary() -> dict[str, object]:
    s = get_settings()
    ai = get_ai_client()
    return {
        "ai": {
            "provider": ai.primary.name,
            "model": ai.primary.model,
            "is_mock": ai.primary.is_mock,
            "fallback_model": s.ai_fallback_model or None,
            "fast_model": s.ai_fast_model or None,
        },
        "voice": {"provider": get_voice_provider().name, **get_voice_provider().session_config().__dict__},
        "embeddings": {"provider": get_embedding_provider().name, "model": get_embedding_provider().model},
        "screen_analysis": s.screen_analysis_provider,
        "storage": s.storage_backend,
    }
