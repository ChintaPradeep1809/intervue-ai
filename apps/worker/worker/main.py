"""Isolated code-execution worker.

Runs separately from the API. Every execution gets a fresh sandbox:

* backend ``docker`` (default, production): one-shot container per run with --network none,
  memory/CPU/PID limits, read-only root FS, tmpfs workdir, dropped capabilities, non-root user and
  no-new-privileges. Code and tests are piped over stdin — nothing from the host is mounted.
* backend ``local`` (development only): subprocess in a temp dir with a stripped environment and a
  wall-clock timeout (plus rlimits on POSIX). Refused when ENVIRONMENT=production and only used
  when EXECUTION_ALLOW_LOCAL=true. It is NOT a security boundary.

SQL runs in-process against an in-memory SQLite database guarded by an authorizer (see
intervue_coding.sql_engine) — no candidate code is executed for SQL.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from intervue_coding.harness import build_payload, parse_output
from intervue_coding.sql_data import DATASETS
from intervue_coding.sql_engine import run_query

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
TOKEN = os.getenv("WORKER_TOKEN", "change-me-worker-token")
BACKEND = os.getenv("EXECUTION_BACKEND", "docker")
ALLOW_LOCAL = os.getenv("EXECUTION_ALLOW_LOCAL", "false").lower() == "true" and ENVIRONMENT != "production"
MAX_OUTPUT = 256 * 1024
IMAGES = {
    "python": os.getenv("SANDBOX_PYTHON_IMAGE", "python:3.12-alpine"),
    "javascript": os.getenv("SANDBOX_NODE_IMAGE", "node:24-alpine"),
    "typescript": os.getenv("SANDBOX_NODE_IMAGE", "node:24-alpine"),
}
SANDBOX_DIR = "/tmp/work"  # noqa: S108 - path inside the throwaway container tmpfs
_sem = asyncio.Semaphore(int(os.getenv("WORKER_CONCURRENCY", "4")))

PY_BOOT = (
    "import json,os,sys;d=json.loads(sys.stdin.read());os.makedirs(d['dir'],exist_ok=True)\n"
    "for n,c in d['files'].items():\n open(os.path.join(d['dir'],n),'w').write(c)\n"
    "os.chdir(d['dir']);exec(compile(open('runner.py').read(),'runner.py','exec'),{'__name__':'__main__'})"
)
NODE_BOOT = (
    "let s='';process.stdin.on('data',c=>s+=c).on('end',async()=>{const d=JSON.parse(s);const fs=require('fs');const p=require('path');"
    "fs.mkdirSync(d.dir,{recursive:true});for(const [n,c] of Object.entries(d.files))fs.writeFileSync(p.join(d.dir,n),c);"
    "process.chdir(d.dir);await import(require('url').pathToFileURL(p.join(d.dir,'runner.mjs')).href);});"
)

app = FastAPI(title="IntervueAI execution worker", docs_url=None, redoc_url=None)


class ExecuteIn(BaseModel):
    language: str = Field(pattern="^(python|javascript|typescript)$")
    code: str = Field(max_length=100_000)
    function_name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    tests: list[dict[str, Any]] = Field(max_length=50)
    timeout_ms: int = Field(default=6000, ge=500, le=15000)


class SqlIn(BaseModel):
    dataset: str
    query: str = Field(max_length=20_000)
    timeout_ms: int = Field(default=3000, ge=200, le=10000)


def _auth(token: str | None) -> None:
    if not token or not hmac.compare_digest(token, TOKEN):
        raise HTTPException(401, "unauthorized")


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


_docker_ok: bool | None = None


def backend() -> str:
    global _docker_ok
    if BACKEND == "docker":
        if _docker_ok is None:
            _docker_ok = _docker_available()
        if _docker_ok:
            return "docker"
        if ALLOW_LOCAL:
            return "local"
        return "unavailable"
    if BACKEND == "local" and ALLOW_LOCAL:
        return "local"
    return "unavailable"


def _docker_cmd(language: str, timeout_s: float, name: str) -> list[str]:
    image = IMAGES[language]
    base = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--init",
        "--name",
        name,
        "--network",
        "none",
        "--memory",
        "256m",
        "--memory-swap",
        "256m",
        "--cpus",
        "0.5",
        "--pids-limit",
        "64",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,size=16m",  # noqa: S108 - container tmpfs
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "65534:65534",
        "--ulimit",
        "nofile=64:64",
        "--ulimit",
        "fsize=1048576:1048576",
        "-e",
        "HOME=/tmp",
        "--stop-timeout",
        "1",
        image,
    ]
    limit = ["timeout", "-s", "KILL", str(max(1, int(timeout_s + 0.999)))]  # busybox timeout inside the container
    if language == "python":
        return base + limit + ["python", "-I", "-c", PY_BOOT]
    return base + limit + ["node", "--max-old-space-size=128", "-e", NODE_BOOT]


def _kill_container(name: str) -> None:
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)


def _local_cmd(language: str, workdir: str) -> list[str]:
    if language == "python":
        return [sys.executable, "-I", "-c", PY_BOOT]
    node = shutil.which("node") or "node"
    return [node, "--max-old-space-size=128", "-e", NODE_BOOT]


def _posix_limits() -> None:  # pragma: no cover - POSIX only
    if sys.platform == "win32":
        return
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    os.setsid()


def _run(cmd: list[str], stdin: str, timeout_s: float, cwd: str | None, env: dict[str, str] | None) -> tuple[str, str, int | None, bool]:
    kwargs: dict[str, Any] = {}
    if sys.platform != "win32" and env is not None:
        kwargs["preexec_fn"] = _posix_limits
    try:
        p = subprocess.run(cmd, input=stdin.encode(), capture_output=True, timeout=timeout_s, cwd=cwd, env=env, **kwargs)
        return p.stdout[:MAX_OUTPUT].decode(errors="replace"), p.stderr[-8000:].decode(errors="replace"), p.returncode, False
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"")[:MAX_OUTPUT].decode(errors="replace")
        return out, "", None, True


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"backend": backend(), "configured_backend": BACKEND, "allow_local": ALLOW_LOCAL, "images": IMAGES}


@app.post("/execute")
async def execute(body: ExecuteIn, x_worker_token: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(x_worker_token)
    be = backend()
    if be == "unavailable":
        raise HTTPException(503, "No safe execution backend is available (Docker not running and local execution disabled).")
    files, marker = build_payload(body.language, body.code, body.function_name, body.tests, SANDBOX_DIR if be == "docker" else "__WORKDIR__")
    timeout_s = body.timeout_ms / 1000
    async with _sem:
        started = time.perf_counter()
        if be == "docker":
            stdin = json.dumps({"dir": SANDBOX_DIR, "files": files})
            name = f"iv-sbx-{uuid.uuid4().hex[:12]}"
            # container start-up time is excluded from the candidate's time budget
            out, err, code, timed_out = await asyncio.to_thread(_run, _docker_cmd(body.language, timeout_s, name), stdin, timeout_s + 8, None, None)
            if timed_out:
                await asyncio.to_thread(_kill_container, name)
            if code == 137 and (time.perf_counter() - started) >= timeout_s:
                timed_out = True  # killed by the in-container timeout (OOM kills are also 137 but happen earlier)
        else:
            tmp = tempfile.mkdtemp(prefix="iv-run-")
            try:
                workdir = os.path.join(tmp, "work")
                files = {n: c.replace("__WORKDIR__", workdir.replace("\\", "/")) for n, c in files.items()}
                stdin = json.dumps({"dir": workdir, "files": files})
                env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""), "HOME": tmp, "TEMP": tmp, "TMP": tmp}
                out, err, code, timed_out = await asyncio.to_thread(_run, _local_cmd(body.language, workdir), stdin, timeout_s, tmp, env)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        runtime_ms = int((time.perf_counter() - started) * 1000)
    payload, other = parse_output(out, marker)
    if timed_out and payload is None:
        return {"status": "timeout", "error": f"Time limit of {body.timeout_ms} ms exceeded", "runtime_ms": runtime_ms, "backend": be, "stdout": other}
    if payload is None:
        msg = err.strip().splitlines()[-1] if err.strip() else "Program exited without producing results"
        if code == 137:
            msg = "Memory limit exceeded"
        return {"status": "error", "error": msg[:1000], "stderr": err[-4000:], "stdout": other, "runtime_ms": runtime_ms, "backend": be}
    return {"status": "ok", "payload": payload, "stdout": other, "stderr": err[-2000:], "runtime_ms": runtime_ms, "backend": be}


@app.post("/sql")
async def sql(body: SqlIn, x_worker_token: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(x_worker_token)
    if body.dataset not in DATASETS:
        raise HTTPException(422, "Unknown dataset")
    result = await asyncio.to_thread(run_query, body.dataset, body.query, body.timeout_ms)
    return result.model_dump()
