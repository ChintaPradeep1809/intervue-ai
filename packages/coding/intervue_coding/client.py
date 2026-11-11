"""HTTP client the API uses to reach the isolated execution worker."""

from __future__ import annotations

from typing import Any

import httpx


class WorkerUnavailable(Exception):
    pass


class WorkerClient:
    def __init__(self, base_url: str, token: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout_seconds

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}{path}", json=body, headers={"X-Worker-Token": self.token})
        except httpx.HTTPError as exc:
            raise WorkerUnavailable(f"Execution worker unreachable: {exc.__class__.__name__}") from exc
        if resp.status_code >= 500 or resp.status_code in (401, 403):
            raise WorkerUnavailable(f"Execution worker error {resp.status_code}")
        data: dict[str, Any] = resp.json()
        return data

    async def execute(self, language: str, code: str, function_name: str, tests: list[dict[str, Any]], timeout_ms: int) -> dict[str, Any]:
        return await self._post("/execute", {"language": language, "code": code, "function_name": function_name, "tests": tests, "timeout_ms": timeout_ms})

    async def sql(self, dataset: str, query: str, timeout_ms: int = 3000) -> dict[str, Any]:
        return await self._post("/sql", {"dataset": dataset, "query": query, "timeout_ms": timeout_ms})

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/health")
            data: dict[str, Any] = resp.json()
            return data
        except Exception as exc:
            raise WorkerUnavailable(str(exc)) from exc
