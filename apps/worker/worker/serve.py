from __future__ import annotations

import os
from pathlib import Path

import uvicorn


def _load_env() -> None:
    env = Path(__file__).resolve().parents[3] / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    _load_env()
    uvicorn.run("worker.main:app", host=os.getenv("WORKER_HOST", "127.0.0.1"), port=int(os.getenv("WORKER_PORT", "8101")), log_level="info")


if __name__ == "__main__":
    main()
