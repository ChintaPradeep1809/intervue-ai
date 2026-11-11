from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.config import get_settings
from app.db import session_factory
from app.logging_setup import configure_logging, request_id_var
from app.routers import admin, auth, documents, interviews, invites, organization, profile, public, ws
from app.services.metrics import metrics
from app.services.usage import load_fx_override, load_pricing_overrides
from intervue_security import RateLimiter

log = logging.getLogger("intervue.api")
limiter = RateLimiter()

# (path prefix, method or "*", limit, window seconds, key: ip|user)
RATE_RULES = [
    ("/api/auth/login", "POST", 10, 60),
    ("/api/auth/register", "POST", 5, 60),
    ("/api/demo/start", "POST", 5, 3600),
    ("/api/documents", "POST", 20, 3600),
    ("/api/interviews", "POST", 30, 3600),
    ("/api/organization/knowledge", "POST", 30, 3600),
]
CODE_RULE = (30, 60)
DEFAULT_RULE = (600, 60)
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request_id_var.set(rid)
        path, method = request.url.path, request.method
        ip = request.client.host if request.client else "?"
        settings = get_settings()

        # CSRF defence for cookie auth: unsafe methods must come from an allowed origin.
        origin = request.headers.get("origin")
        if method in UNSAFE and origin and origin not in settings.cors_origins and origin != settings.public_web_url:
            return JSONResponse({"detail": "Request origin not allowed."}, status_code=403, headers={"x-request-id": rid})

        if settings.environment != "test":
            rule = next(((lim, win) for p, m, lim, win in RATE_RULES if path.startswith(p) and (m == "*" or m == method)), None)
            if rule is None and "/code/" in path:
                rule = CODE_RULE
            limit, window = rule or DEFAULT_RULE
            bucket = next((p for p, *_ in RATE_RULES if path.startswith(p)), "/code" if "/code/" in path else "default")
            ok, retry = limiter.hit(f"{ip}:{bucket}:{method}", limit, window)
            if not ok:
                metrics.incr("rate_limited")
                return JSONResponse(
                    {"detail": "Too many requests. Please wait a moment and try again."},
                    status_code=429,
                    headers={"Retry-After": str(int(retry) + 1), "x-request-id": rid},
                )

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            metrics.error("http", f"{method} {path}: {exc}", rid)
            log.exception("unhandled_error", extra={"path": path})
            response = JSONResponse({"detail": "Something went wrong on our side. Please try again.", "request_id": rid}, status_code=500)
        ms = (time.perf_counter() - started) * 1000
        metrics.observe("http", ms)
        if response.status_code >= 500:
            metrics.incr("http_5xx")
        response.headers["x-request-id"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if path.startswith("/api/") and not path.startswith("/api/files/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if ms > 1500:
            log.info("slow_request", extra={"path": path, "ms": round(ms)})
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    task = None
    try:
        async with session_factory()() as db:
            await load_pricing_overrides(db)
            await load_fx_override(db)
    except Exception:
        log.warning("pricing_overrides_unavailable")
    if get_settings().environment != "test":
        from app.services.orchestrator import tick_loop

        task = asyncio.create_task(tick_loop())
    yield
    if task:
        task.cancel()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=f"{s.brand_name} API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if s.environment != "production" else None,
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        first = errors[0] if errors else {"field": "", "message": "Invalid input"}
        msg = f"{first['field']}: {first['message']}" if first["field"] else first["message"]
        return JSONResponse({"detail": msg, "errors": errors}, status_code=422)

    @app.exception_handler(HTTPException)
    async def http_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)

    for r in (public.router, auth.router, profile.router, documents.router, interviews.router, invites.router, organization.router, admin.router, ws.router):
        app.include_router(r)
    return app


app = create_app()
