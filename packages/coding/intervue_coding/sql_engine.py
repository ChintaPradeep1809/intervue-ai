"""SQL sandbox: an in-memory SQLite database per execution with a read-only authorizer.

The candidate's query can only read the seeded tables. ATTACH, PRAGMA, writes, extension loading
and temp objects are denied; runaway queries are cut off by a progress handler deadline.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from pydantic import BaseModel

from intervue_coding.sql_data import DATASETS

_ALLOWED = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}


class SqlResult(BaseModel):
    columns: list[str] = []
    rows: list[list[Any]] = []
    truncated: bool = False
    error: str | None = None
    runtime_ms: int = 0
    status: str = "ok"  # ok | error | timeout


def _authorizer(action: int, arg1: Any, arg2: Any, dbname: Any, source: Any) -> int:
    if action in _ALLOWED:
        if action == sqlite3.SQLITE_FUNCTION and str(arg2).lower() in {"load_extension", "readfile", "writefile", "edit"}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def build_database(dataset: str) -> sqlite3.Connection:
    ds = DATASETS[dataset]
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.executescript(ds.ddl)
    for table, rows in ds.rows.items():
        if not rows:
            continue
        cols = list(rows[0].keys())
        conn.executemany(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            [tuple(r[c] for c in cols) for r in rows],
        )
    return conn


def run_query(dataset: str, query: str, timeout_ms: int = 3000, max_rows: int = 500) -> SqlResult:
    q = query.strip().rstrip(";").strip()
    if not q:
        return SqlResult(error="Query is empty", status="error")
    if ";" in q:
        return SqlResult(error="Only a single statement is allowed", status="error")
    if len(q) > 20_000:
        return SqlResult(error="Query is too long", status="error")
    conn = build_database(dataset)
    deadline = time.monotonic() + timeout_ms / 1000
    timed_out = False

    def _progress() -> int:
        nonlocal timed_out
        if time.monotonic() > deadline:
            timed_out = True
            return 1
        return 0

    conn.set_progress_handler(_progress, 2000)
    conn.set_authorizer(_authorizer)
    started = time.perf_counter()
    try:
        cur = conn.execute(q)
        columns = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        return SqlResult(
            columns=columns,
            rows=[list(r) for r in rows[:max_rows]],
            truncated=truncated,
            runtime_ms=int((time.perf_counter() - started) * 1000),
        )
    except sqlite3.DatabaseError as exc:
        if timed_out:
            return SqlResult(error=f"Query exceeded {timeout_ms} ms time limit", status="timeout", runtime_ms=timeout_ms)
        msg = str(exc)
        if "not authorized" in msg:
            msg = "Only read-only SELECT queries on the provided tables are allowed"
        return SqlResult(error=msg, status="error", runtime_ms=int((time.perf_counter() - started) * 1000))
    finally:
        conn.close()
