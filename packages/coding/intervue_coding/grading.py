"""Grading of sandbox results against expected outputs (expected values never leave the API)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from intervue_coding.problems import CodingProblem
from intervue_coding.sql_data import SqlProblem
from intervue_coding.sql_engine import SqlResult


class TestOutcome(BaseModel):
    name: str
    passed: bool
    hidden: bool
    args: Any = None
    expected: Any = None
    actual: Any = None
    error: str | None = None
    stdout: str = ""
    ms: int = 0


class GradeResult(BaseModel):
    status: str  # passed | failed | error | timeout
    passed: int
    total: int
    outcomes: list[TestOutcome]
    error: str | None = None
    stdout: str = ""
    runtime_ms: int = 0


def _canon(v: Any, unordered: bool) -> Any:
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, dict):
        return {str(k): _canon(x, unordered) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        items = [_canon(x, unordered) for x in v]
        if unordered:
            items.sort(key=lambda x: json.dumps(x, sort_keys=True, default=str))
        return items
    return v


def values_equal(actual: Any, expected: Any, unordered: bool = False) -> bool:
    return _canon(actual, unordered) == _canon(expected, unordered)


def grade_code(problem: CodingProblem, worker_result: dict[str, Any], include_hidden: bool) -> GradeResult:
    tests = [t for t in problem.tests if include_hidden or not t.hidden]
    status = worker_result.get("status", "error")
    runtime = int(worker_result.get("runtime_ms", 0))
    if status == "timeout":
        return GradeResult(
            status="timeout", passed=0, total=len(tests), outcomes=[], error=worker_result.get("error") or "Time limit exceeded", runtime_ms=runtime
        )
    payload = worker_result.get("payload") or {}
    if status != "ok" or "fatal" in payload or "results" not in payload:
        err = payload.get("fatal") or worker_result.get("error") or worker_result.get("stderr") or "Execution failed"
        return GradeResult(
            status="error",
            passed=0,
            total=len(tests),
            outcomes=[],
            error=str(err)[-1500:],
            stdout=payload.get("stdout", worker_result.get("stdout", "")),
            runtime_ms=runtime,
        )
    by_name = {r["name"]: r for r in payload["results"]}
    outcomes = []
    for t in tests:
        r = by_name.get(t.name)
        if r is None:
            outcomes.append(TestOutcome(name=t.name, passed=False, hidden=t.hidden, error="No result"))
            continue
        ok = bool(r.get("ok")) and values_equal(r.get("value"), t.expected, problem.compare == "unordered")
        outcomes.append(
            TestOutcome(
                name=t.name,
                passed=ok,
                hidden=t.hidden,
                args=None if t.hidden else t.args,
                expected=None if t.hidden else t.expected,
                actual=None if t.hidden else r.get("value"),
                error=r.get("error"),
                stdout=r.get("stdout", ""),
                ms=int(r.get("ms", 0)),
            )
        )
    passed = sum(o.passed for o in outcomes)
    return GradeResult(
        status="passed" if passed == len(tests) else "failed",
        passed=passed,
        total=len(tests),
        outcomes=outcomes,
        stdout=worker_result.get("stdout", ""),
        runtime_ms=runtime,
    )


def _norm_rows(rows: list[list[Any]], ordered: bool) -> list[tuple[Any, ...]]:
    out = [tuple(round(v, 2) if isinstance(v, float) else v for v in r) for r in rows]
    return out if ordered else sorted(out, key=lambda r: json.dumps(r, default=str))


def grade_sql(problem: SqlProblem, candidate: SqlResult, reference: SqlResult) -> GradeResult:
    if candidate.status != "ok":
        return GradeResult(
            status="timeout" if candidate.status == "timeout" else "error",
            passed=0,
            total=3,
            outcomes=[],
            error=candidate.error,
            runtime_ms=candidate.runtime_ms,
        )
    checks = [
        TestOutcome(
            name="column count",
            passed=len(candidate.columns) == len(reference.columns),
            hidden=False,
            expected=len(reference.columns),
            actual=len(candidate.columns),
        ),
        TestOutcome(
            name="row count", passed=len(candidate.rows) == len(reference.rows), hidden=False, expected=len(reference.rows), actual=len(candidate.rows)
        ),
        TestOutcome(
            name="result values" + (" (ordered)" if problem.order_matters else ""),
            hidden=True,
            passed=_norm_rows(candidate.rows, problem.order_matters) == _norm_rows(reference.rows, problem.order_matters),
        ),
    ]
    passed = sum(c.passed for c in checks)
    return GradeResult(status="passed" if passed == 3 else "failed", passed=passed, total=3, outcomes=checks, runtime_ms=candidate.runtime_ms)
