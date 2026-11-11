"""Provider pricing configuration and cost estimation. Prices are data, never code constants."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ModelPrice(BaseModel):
    input_per_mtok: float = 0.0
    output_per_mtok: float = 0.0
    cache_read_per_mtok: float = 0.0


class PricingConfig(BaseModel):
    currency: str = "USD"
    llm: dict[str, ModelPrice] = Field(default_factory=dict)  # key: "provider:model" or "provider:*"
    voice_per_minute: dict[str, float] = Field(default_factory=dict)  # key: provider
    tts_per_1k_chars: dict[str, float] = Field(default_factory=dict)
    embedding_per_mtok: dict[str, float] = Field(default_factory=dict)
    execution_per_second: float = 0.0
    storage_per_gb_month: float = 0.0

    def llm_price(self, provider: str, model: str) -> ModelPrice:
        return self.llm.get(f"{provider}:{model}") or self.llm.get(f"{provider}:*") or ModelPrice()

    def llm_cost(self, provider: str, model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0) -> tuple[float, float]:
        p = self.llm_price(provider, model)
        uncached = max(0, input_tokens - cache_read_tokens)
        input_cost = (uncached * p.input_per_mtok + cache_read_tokens * p.cache_read_per_mtok) / 1_000_000
        return input_cost, output_tokens * p.output_per_mtok / 1_000_000

    def voice_cost(self, provider: str, seconds: float, tts_chars: int = 0) -> float:
        per_min = self.voice_per_minute.get(provider, 0.0)
        per_k = self.tts_per_1k_chars.get(provider, 0.0)
        return seconds / 60.0 * per_min + tts_chars / 1000.0 * per_k

    def embedding_cost(self, provider: str, tokens: int) -> float:
        return tokens * self.embedding_per_mtok.get(provider, 0.0) / 1_000_000

    def execution_cost(self, seconds: float) -> float:
        return seconds * self.execution_per_second

    def storage_cost(self, num_bytes: int, months: float = 1.0) -> float:
        return num_bytes / 1_073_741_824 * self.storage_per_gb_month * months


def load_pricing(path: str | Path | None, overrides: dict[str, Any] | None = None) -> PricingConfig:
    data: dict[str, Any] = {}
    if path and Path(path).exists():
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    if overrides:
        data.update(overrides)
    return PricingConfig.model_validate(data)
