"""Embedding providers.

`HashingEmbeddingProvider` is a local, dependency-free feature-hashing embedder (word unigrams +
bigrams, signed hashing, L2-normalised). It is good enough for keyword-heavy retrieval over
interview guidelines and question banks, and it keeps RAG working without credentials. Swap in a
hosted embedding model via `EMBEDDING_PROVIDER` when one is configured.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import re

from intervue_ai.base import EmbeddingProvider

_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.\-]*")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class HashingEmbeddingProvider(EmbeddingProvider):
    name = "local-hashing"
    model = "hashing-384"

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dimensions
        toks = tokenize(text)
        feats = toks + [f"{a} {b}" for a, b in itertools.pairwise(toks)]
        for f in feats:
            h = hashlib.blake2b(f.encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self.dimensions
            sign = 1.0 if h[4] & 1 else -1.0
            v[idx] += sign
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    async def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        tokens = sum(len(tokenize(t)) for t in texts)
        return [self._vec(t) for t in texts], tokens


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))
