from __future__ import annotations

from app.config import get_settings
from intervue_coding import WorkerClient


def worker_client() -> WorkerClient:
    s = get_settings()
    return WorkerClient(s.worker_url, s.worker_token, timeout_seconds=30)
