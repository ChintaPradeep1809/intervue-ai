"""Test configuration: isolated SQLite database, mock AI, local storage in a temp dir, stub worker."""

from __future__ import annotations

import io
import os
import tempfile
from collections.abc import Iterator
from typing import Any

import pytest

_TMP = tempfile.mkdtemp(prefix="intervue-tests-")
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": f"sqlite+aiosqlite:///{_TMP}/test.db",
        "AUTH_SECRET": "test-secret-0123456789-0123456789-0123456789",
        "AI_PROVIDER": "mock",
        "VOICE_PROVIDER": "browser",
        "STORAGE_BACKEND": "local",
        "STORAGE_LOCAL_ROOT": f"{_TMP}/storage",
        "WORKER_TOKEN": "test-worker-token",
        "DEMO_ENABLED": "true",
        "CORS_ORIGINS": '["http://testserver"]',
        "PUBLIC_WEB_URL": "http://testserver",
    }
)


class StubWorker:
    """In-process stand-in for the execution worker: real SQL sandbox, scripted code results."""

    async def sql(self, dataset: str, query: str, timeout_ms: int = 3000) -> dict[str, Any]:
        from intervue_coding import run_query

        return run_query(dataset, query, timeout_ms).model_dump()

    async def execute(self, language: str, code: str, function_name: str, tests: list[dict[str, Any]], timeout_ms: int) -> dict[str, Any]:
        from intervue_coding import PROBLEMS

        # Evaluate Python solutions in-process ONLY inside tests (the real worker sandboxes this).
        ns: dict[str, Any] = {}
        try:
            exec(compile(code, "solution.py", "exec"), ns)
            fn = ns[function_name]
        except Exception as exc:
            return {"status": "ok", "payload": {"fatal": str(exc)}, "runtime_ms": 1, "backend": "stub"}
        results = []
        for t in tests:
            try:
                results.append({"name": t["name"], "ok": True, "value": fn(*t["args"]), "stdout": "", "ms": 0})
            except Exception as exc:
                results.append({"name": t["name"], "ok": False, "error": str(exc), "stdout": "", "ms": 0})
        assert PROBLEMS
        return {"status": "ok", "payload": {"results": results}, "runtime_ms": 3, "backend": "stub"}

    async def health(self) -> dict[str, Any]:
        return {"backend": "stub"}


@pytest.fixture(scope="session")
def app_instance():  # type: ignore[no-untyped-def]
    from sqlalchemy import create_engine

    from app import models  # noqa: F401
    from app.db import Base

    url = os.environ["DATABASE_URL"].replace("sqlite+aiosqlite", "sqlite")
    eng = create_engine(url)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    eng.dispose()

    import app.services.coding as coding_service
    from app.main import app

    coding_service.worker_client = lambda: StubWorker()  # type: ignore[assignment]
    import app.routers.interviews as iv_router

    iv_router.worker_client = lambda: StubWorker()  # type: ignore[assignment]
    _seed_bank()
    return app


def _seed_bank() -> None:
    import asyncio

    from app.db import session_factory
    from app.models import Plan, Question
    from intervue_engine import QUESTIONS

    async def go() -> None:
        async with session_factory()() as db:
            for q in QUESTIONS:
                db.add(
                    Question(
                        bank_key=q.id,
                        topic=q.topic,
                        kind=q.kind,
                        difficulty=q.difficulty,
                        text=q.text,
                        concepts=[c.model_dump() for c in q.concepts],
                        followups=[f.model_dump() for f in q.followups],
                        roles=q.roles,
                    )
                )
            db.add(Plan(key="free", name="Free", limits={"interviews_per_month": 3}))
            db.add(Plan(key="college", name="College", audience="organization", limits={"interviews_per_month": 500}))
            await db.commit()

    asyncio.run(go())


@pytest.fixture
def client(app_instance) -> Iterator[Any]:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    with TestClient(app_instance, base_url="http://testserver") as c:
        yield c


def register(client: Any, email: str, name: str = "Test User", account_type: str = "candidate", password: str = "Password!123") -> dict[str, Any]:
    r = client.post("/api/auth/register", json={"email": email, "password": password, "full_name": name, "account_type": account_type})
    assert r.status_code == 201, r.text
    return r.json()


def make_docx(lines: list[str]) -> bytes:
    import docx

    d = docx.Document()
    for ln in lines:
        d.add_paragraph(ln)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
