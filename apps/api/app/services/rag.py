"""Organisation knowledge base: parse → chunk → embed → store → retrieve.

Embeddings are stored as JSON arrays and scored in Python, which is fine for thousands of chunks
per organisation. For larger corpora switch the column to pgvector (see docs/AI_ARCHITECTURE.md).
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeChunk, KnowledgeDocument
from app.services.ai import get_embedding_provider
from app.services.usage import pricing, record
from intervue_ai import cosine

CHUNK_CHARS = 1200
OVERLAP = 150


def chunk_text(text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[#\-*\d])", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        if len(cur) + len(p) + 1 <= CHUNK_CHARS:
            cur = f"{cur}\n{p}".strip()
            continue
        if cur:
            chunks.append(cur)
        while len(p) > CHUNK_CHARS:
            chunks.append(p[:CHUNK_CHARS])
            p = p[CHUNK_CHARS - OVERLAP :]
        cur = p
    if cur:
        chunks.append(cur)
    return chunks


async def ingest(db: AsyncSession, org_id: uuid.UUID, title: str, kind: str, filename: str, text: str) -> KnowledgeDocument:
    doc = KnowledgeDocument(organization_id=org_id, title=title, kind=kind, filename=filename)
    db.add(doc)
    await db.flush()
    chunks = chunk_text(text)
    provider = get_embedding_provider()
    vectors, tokens = await provider.embed(chunks) if chunks else ([], 0)
    for i, (c, v) in enumerate(zip(chunks, vectors, strict=False)):
        db.add(KnowledgeChunk(document_id=doc.id, organization_id=org_id, ordinal=i, content=c, embedding=v))
    doc.chunk_count = len(chunks)
    record("embedding", provider.name, tokens, pricing().embedding_cost(provider.name, tokens), task="ingest", tokens=tokens)
    return doc


async def retrieve(db: AsyncSession, org_id: uuid.UUID, query: str, k: int = 4) -> list[tuple[float, KnowledgeChunk]]:
    provider = get_embedding_provider()
    [qv], tokens = await provider.embed([query])
    record("embedding", provider.name, tokens, pricing().embedding_cost(provider.name, tokens), task="retrieve", tokens=tokens)
    rows = (await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.organization_id == org_id))).scalars().all()
    scored = sorted(((cosine(qv, r.embedding), r) for r in rows), key=lambda x: -x[0])
    return [s for s in scored[:k] if s[0] > 0.05]
