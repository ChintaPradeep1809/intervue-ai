"""Code execution security and grading tests."""

import json
import shutil
import sys

import pytest

from intervue_coding import PROBLEMS, get_problem, get_sql_problem, grade_code, grade_sql, run_query
from intervue_coding.harness import build_payload, parse_output


def test_sql_sandbox_is_read_only():
    assert run_query("retail", "SELECT COUNT(*) FROM orders").rows[0][0] > 0
    for q in [
        "DELETE FROM orders",
        "DROP TABLE orders",
        "INSERT INTO orders VALUES (1,1,'x','y')",
        "ATTACH DATABASE 'x.db' AS x",
        "PRAGMA writable_schema = 1",
        "SELECT load_extension('x')",
        "CREATE TABLE t (a int)",
    ]:
        r = run_query("retail", q)
        assert r.status == "error", q
    assert run_query("retail", "SELECT 1; DROP TABLE orders").status == "error"


def test_sql_sandbox_timeout():
    r = run_query("retail", "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c", timeout_ms=300)
    assert r.status == "timeout"


def test_sql_grading_reference_passes_and_wrong_fails():
    for p in [get_sql_problem("sql-top-customers"), get_sql_problem("sql-latest-order"), get_sql_problem("sql-category-rank")]:
        ref = run_query(p.dataset, p.reference_sql)
        assert ref.status == "ok" and ref.rows
        assert grade_sql(p, ref, ref).status == "passed"
        wrong = run_query(p.dataset, "SELECT * FROM customers LIMIT 5")
        assert grade_sql(p, wrong, ref).status == "failed"


def test_code_grading_never_leaks_hidden_expectations():
    p = get_problem("two-sum")
    wr = {"status": "ok", "payload": {"results": [{"name": t.name, "ok": True, "value": [9, 9]} for t in p.tests]}, "runtime_ms": 1}
    g = grade_code(p, wr, include_hidden=True)
    assert g.passed == 0
    for o in g.outcomes:
        if o.hidden:
            assert o.expected is None and o.args is None and o.actual is None


def test_harness_payload_contains_no_expected_values():
    p = get_problem("merge-intervals")
    files, marker = build_payload("python", "def merge_intervals(x):\n    return x\n", p.function_name, [t.model_dump() for t in p.tests], "/tmp/work")
    data = json.loads(files["input.json"])
    assert all("expected" not in t for t in data["tests"])
    payload, other = parse_output(f"noise\n{marker}{json.dumps({'results': []})}\n", marker)
    assert payload == {"results": []} and other == "noise"


def test_all_problems_have_starters_and_tests():
    for p in PROBLEMS:
        assert {"python", "javascript", "typescript"} <= set(p.starter)
        assert any(t.hidden for t in p.tests) and any(not t.hidden for t in p.tests)


def test_worker_requires_token_and_restricts_docker_flags(monkeypatch):
    monkeypatch.setenv("WORKER_TOKEN", "tok")
    import importlib

    import worker.main as wm

    wm = importlib.reload(wm)
    from fastapi.testclient import TestClient

    c = TestClient(wm.app)
    assert c.post("/execute", json={"language": "python", "code": "x", "function_name": "f", "tests": []}).status_code == 401
    assert c.post("/sql", json={"dataset": "retail", "query": "select 1"}, headers={"X-Worker-Token": "bad"}).status_code == 401
    assert c.post("/sql", json={"dataset": "retail", "query": "delete from orders"}, headers={"X-Worker-Token": "tok"}).json()["status"] == "error"
    cmd = wm._docker_cmd("python", 5, "iv-sbx-test")
    for flag in ["--network", "none", "--read-only", "--cap-drop", "ALL", "--pids-limit", "--memory", "no-new-privileges", "--init", "65534:65534"]:
        assert flag in cmd
    assert "-v" not in cmd and "--privileged" not in cmd
    bad = c.post("/execute", json={"language": "ruby", "code": "x", "function_name": "f", "tests": []}, headers={"X-Worker-Token": "tok"})
    assert bad.status_code == 422
    bad = c.post("/execute", json={"language": "python", "code": "x", "function_name": "f; rm -rf /", "tests": []}, headers={"X-Worker-Token": "tok"})
    assert bad.status_code == 422


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_local_backend_runs_and_enforces_timeout(monkeypatch):
    """Exercises the dev 'local' backend end-to-end (the docker backend is used in production)."""
    monkeypatch.setenv("WORKER_TOKEN", "tok")
    monkeypatch.setenv("EXECUTION_BACKEND", "local")
    monkeypatch.setenv("EXECUTION_ALLOW_LOCAL", "true")
    import importlib

    import worker.main as wm

    wm = importlib.reload(wm)
    from fastapi.testclient import TestClient

    c = TestClient(wm.app)
    h = {"X-Worker-Token": "tok"}
    ok = c.post(
        "/execute",
        headers=h,
        json={
            "language": "python",
            "code": "def add(a, b):\n    print('dbg')\n    return a + b\n",
            "function_name": "add",
            "tests": [{"name": "t", "args": [2, 3]}],
            "timeout_ms": 5000,
        },
    ).json()
    assert ok["status"] == "ok" and ok["payload"]["results"][0]["value"] == 5 and ok["payload"]["results"][0]["stdout"].strip() == "dbg"
    slow = c.post(
        "/execute",
        headers=h,
        json={"language": "python", "code": "def f():\n    while True: pass\n", "function_name": "f", "tests": [{"name": "t", "args": []}], "timeout_ms": 1000},
    ).json()
    assert slow["status"] == "timeout"
    ts = c.post(
        "/execute",
        headers=h,
        json={
            "language": "typescript",
            "code": "export function add(a: number, b: number): number { return a + b; }",
            "function_name": "add",
            "tests": [{"name": "t", "args": [1, 2]}],
            "timeout_ms": 8000,
        },
    ).json()
    assert ts["status"] == "ok" and ts["payload"]["results"][0]["value"] == 3, ts
    assert sys.platform  # keep import used
