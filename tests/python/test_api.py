"""API critical-path, authorization and tenant-isolation tests."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from .conftest import make_docx, register

RESUME_LINES = ["Asha Verma", "Data Engineer with 2 years of experience.", "Skills: Python, SQL, PySpark, AWS Glue, Athena, Airflow."]


def uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def test_register_login_logout_and_me(client):
    email = uniq("cand")
    u = register(client, email, "Asha Verma")
    assert u["role"] == "candidate" and u["onboarding_completed"] is False
    assert client.post("/api/auth/register", json={"email": email, "password": "Password!123", "full_name": "x"}).status_code == 409
    assert client.get("/api/auth/me").json()["email"] == email
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": email, "password": "wrong-password"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": email.upper(), "password": "Password!123"})
    assert r.status_code == 200 and "iv_session" in r.cookies
    assert "httponly" in r.headers["set-cookie"].lower()


def test_password_policy_and_validation_errors(client):
    r = client.post("/api/auth/register", json={"email": "not-an-email", "password": "short", "full_name": "x"})
    assert r.status_code == 422 and "detail" in r.json()


def test_csrf_origin_check(client):
    r = client.post("/api/auth/login", json={"email": "a@b.co", "password": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_protected_routes_require_auth(client):
    client.cookies.clear()
    for path in ["/api/interviews", "/api/me/profile", "/api/organization", "/api/admin/command-center"]:
        assert client.get(path).status_code == 401, path


def test_resume_and_jd_upload(client):
    register(client, uniq("docs"))
    docx = make_docx(RESUME_LINES)
    r = client.post("/api/documents/resume", files={"file": ("cv.docx", docx, "application/octet-stream")})
    assert r.status_code == 201, r.text
    assert {"Python", "SQL", "PySpark", "AWS Glue"} <= set(r.json()["detected_skills"])
    bad = client.post("/api/documents/resume", files={"file": ("cv.pdf", b"MZ fake exe", "application/pdf")})
    assert bad.status_code == 422
    jd = client.post("/api/documents/jd", json={"title": "DE", "text": "We need Kafka, Redshift and Airflow experience for this data engineering role."})
    assert jd.status_code == 201 and "Apache Kafka" in jd.json()["detected_skills"]
    up = client.post("/api/documents/jd/upload", files={"file": ("jd.txt", b"Looking for a Python developer with FastAPI and Docker.", "text/plain")})
    assert up.status_code == 201
    url = client.get(f"/api/documents/resume/{r.json()['id']}/url").json()["url"]
    assert client.get(url).status_code == 200
    assert client.get(url.replace("sig=", "sig=0")).status_code == 403


def _create_interview(client, **kw) -> dict[str, Any]:
    body = {"role_key": "aws_data_engineer", "interview_type": "technical", "duration_minutes": 30, "difficulty": "medium", **kw}
    r = client.post("/api/interviews", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _drive_ws(client, iid: str, answer_fn, code_fn=None, max_steps: int = 80) -> list[str]:
    ticket = client.post(f"/api/interviews/{iid}/ws-ticket").json()["ticket"]
    events: list[str] = []
    with client.websocket_connect(f"/ws/interviews/{iid}?ticket={ticket}") as ws:
        state = json.loads(ws.receive_text())
        assert state["event_type"] == "STATE_SYNC"
        ws.send_text(json.dumps({"type": "START"}))
        for _ in range(max_steps * 6):
            msg = json.loads(ws.receive_text())
            events.append(msg["event_type"])
            if msg["event_type"] == "INTERVIEW_COMPLETED":
                break
            if msg["event_type"] == "STATE_SYNC":
                s = msg["payload"]
                if s["next_action"] == "WAIT_FOR_ANSWER":
                    ws.send_text(json.dumps({"type": "ANSWER", "text": answer_fn(s), "source": "typed"}))
                elif s["next_action"] == "WAIT_FOR_CODE" and code_fn:
                    code_fn(s)
    return events


def test_full_interview_flow_with_report(client):
    register(client, uniq("flow"), "Flow Candidate")
    client.post("/api/documents/resume", files={"file": ("cv.docx", make_docx(RESUME_LINES), "application/octet-stream")})
    iv = _create_interview(client)
    assert iv["status"] == "planned" and iv["plan"]["rounds"][0]["kind"] == "introduction"
    assert {s["name"] for s in iv["analysis"]["skills"]} >= {"Python", "SQL"}
    # cannot open the socket before consenting
    t = client.post(f"/api/interviews/{iv['id']}/ws-ticket").json()["ticket"]
    with client.websocket_connect(f"/ws/interviews/{iv['id']}?ticket={t}") as ws:
        ws.receive_text()
        ws.send_text(json.dumps({"type": "START"}))
        assert json.loads(ws.receive_text())["event_type"] == "ERROR"
    assert client.post(f"/api/interviews/{iv['id']}/consent", json={"microphone": True, "ai_processing": False, "data_retention_ack": True}).status_code == 422
    assert client.post(f"/api/interviews/{iv['id']}/consent", json={"microphone": True, "ai_processing": True, "data_retention_ack": True}).status_code == 200

    def answer(s):
        return "I would use a window function with row_number partition by key because it is a single pass; the trade-off is memory, for example on 1 TB."

    events = _drive_ws(client, iv["id"], answer)
    for e in ["INTERVIEW_STARTED", "QUESTION_STARTED", "AI_SPEAKING", "TRANSCRIPT_FINAL", "ROUND_COMPLETED", "INTERVIEW_COMPLETED"]:
        assert e in events, e
    detail = client.get(f"/api/interviews/{iv['id']}").json()
    assert detail["status"] == "completed" and detail["overall_score"] is not None
    rep = client.get(f"/api/interviews/{iv['id']}/report").json()["report"]
    assert rep["overall_score"] == detail["overall_score"]
    for ev_list in rep["category_evidence"].values():
        for ev in ev_list:
            if ev["kind"] == "quote":
                assert ev["quote"].lower().replace("  ", " ")[:20] in answer({}).lower() or ev["source"] != "transcript"
    tr = client.get(f"/api/interviews/{iv['id']}/transcript").json()["items"]
    assert tr[0]["speaker"] == "interviewer" and any(t["speaker"] == "candidate" for t in tr)


def test_coding_round_run_and_submit(client):
    register(client, uniq("coder"))
    iv = _create_interview(client, interview_type="coding")
    client.post(f"/api/interviews/{iv['id']}/consent", json={"microphone": False, "ai_processing": True, "data_retention_ack": True, "screen_share": True})
    results: dict[str, Any] = {}

    def code(s):
        problem = s["coding"]["problem"]
        if problem["id"] in results:
            return
        lang = s["coding"]["language"]
        if s["coding"]["is_sql"]:
            from intervue_coding import get_sql_problem

            src = get_sql_problem(problem["id"]).reference_sql
        else:
            src = SOLUTIONS[problem["id"]]
        run = client.post(f"/api/interviews/{iv['id']}/code/run", json={"code": "def nope(:", "language": lang}).json()
        results[problem["id"]] = (run, client.post(f"/api/interviews/{iv['id']}/code/submit", json={"code": src, "language": lang}).json())

    _drive_ws(client, iv["id"], lambda s: "The time complexity is O(n log n) because of the sort, and space is linear.", code)
    assert len(results) == 2  # python round + SQL round for the AWS Data Engineer coding interview
    for run, submit in results.values():
        assert run["status"] in ("error", "failed")
        assert submit["status"] == "passed", submit
    rep = client.get(f"/api/interviews/{iv['id']}/report").json()["report"]
    assert len(rep["coding_summary"]) == 2 and all(c["passed"] == c["total"] for c in rep["coding_summary"])
    sessions = client.get(f"/api/interviews/{iv['id']}/code").json()["sessions"]
    assert sessions and len(sessions[0]["executions"]) >= 2


SOLUTIONS = {
    "latest-record-per-key": "def latest_records(records):\n    best = {}\n    for r in records:\n        k = r['customer_id']\n        if k not in best or r['updated_at'] >= best[k]['updated_at']:\n            best[k] = r\n    return [best[k] for k in sorted(best)]\n",
    "sessionize-events": "def count_sessions(events, gap):\n    by = {}\n    for u, t in events:\n        by.setdefault(u, []).append(t)\n    out = {}\n    for u, ts in by.items():\n        ts.sort()\n        out[u] = 1 + sum(1 for a, b in zip(ts, ts[1:]) if b - a > gap)\n    return out\n",
    "top-k-frequent": "from collections import Counter\ndef top_k(words, k):\n    c = Counter(words)\n    return sorted(c, key=lambda w: (-c[w], w))[:k]\n",
    "merge-intervals": "def merge_intervals(intervals):\n    out = []\n    for s, e in sorted(intervals):\n        if out and s <= out[-1][1]:\n            out[-1][1] = max(out[-1][1], e)\n        else:\n            out.append([s, e])\n    return out\n",
    "validate-records": "def validate_records(records):\n    seen=set(); c={'missing_id':0,'negative_amount':0,'duplicate_id':0,'valid':0}\n    for r in records:\n        bad=False\n        if not r.get('order_id'):\n            c['missing_id']+=1; bad=True\n        if r['amount']<0:\n            c['negative_amount']+=1; bad=True\n        if r.get('order_id') and r['order_id'] in seen:\n            c['duplicate_id']+=1; bad=True\n        if r.get('order_id'): seen.add(r['order_id'])\n        if not bad: c['valid']+=1\n    return c\n",
    "two-sum": "def two_sum(nums, target):\n    s = {}\n    for i, n in enumerate(nums):\n        if target - n in s:\n            return [s[target - n], i]\n        s[n] = i\n",
}


def test_candidate_cannot_access_other_candidates_interview(client):
    register(client, uniq("owner"))
    iv = _create_interview(client)
    client.cookies.clear()
    register(client, uniq("intruder"))
    assert client.get(f"/api/interviews/{iv['id']}").status_code == 404
    assert client.get(f"/api/interviews/{iv['id']}/transcript").status_code == 404
    assert client.post(f"/api/interviews/{iv['id']}/ws-ticket").status_code == 404
    assert client.delete(f"/api/interviews/{iv['id']}").status_code == 404
    # a ticket for one interview cannot be replayed against another
    mine = _create_interview(client)
    t = client.post(f"/api/interviews/{mine['id']}/ws-ticket").json()["ticket"]
    from starlette.websockets import WebSocketDisconnect

    try:
        with client.websocket_connect(f"/ws/interviews/{iv['id']}?ticket={t}") as ws:
            ws.receive_text()
        raise AssertionError("socket should have been rejected")
    except WebSocketDisconnect as exc:
        assert exc.code == 4401


def _org_with_invite(client, name: str) -> tuple[dict[str, Any], str]:
    register(client, uniq(f"admin-{name}"), f"Admin {name}", account_type="organization")
    org = client.post("/api/organizations", json={"name": f"Org {name} {uuid.uuid4().hex[:4]}", "kind": "college"}).json()
    tmpl = client.post(
        "/api/organization/templates",
        json={
            "name": f"Campus {name}",
            "role_key": "aws_data_engineer",
            "difficulty": "easy",
            "rounds": [
                {"kind": "introduction", "minutes": 2, "topics": ["introduction"]},
                {"kind": "technical", "minutes": 6, "topics": ["sql", "pyspark"], "question_count": 2},
            ],
            "scoring_weights": {"sql": 60, "pyspark": 40},
        },
    )
    assert tmpl.status_code == 201, tmpl.text
    inv = client.post(f"/api/organization/templates/{tmpl.json()['id']}/invites", json={"label": "drive", "max_uses": 5}).json()
    return org, inv["token"]


def test_organization_workflow_and_tenant_isolation(client):
    org_a, token_a = _org_with_invite(client, "A")
    admin_a_cookies = dict(client.cookies)
    client.cookies.clear()
    org_b, _ = _org_with_invite(client, "B")
    admin_b_cookies = dict(client.cookies)
    client.cookies.clear()

    # candidate takes org A's interview through the invite link
    assert client.get(f"/api/invites/{token_a}").json()["template"]["name"] == "Campus A"
    register(client, uniq("student"), "Student One")
    iv = client.post(f"/api/invites/{token_a}/accept").json()
    assert iv["organization_id"] == org_a["id"]
    assert [w["topic"] for w in iv["plan"]["skill_weights"]] == ["sql", "pyspark"]  # template scoring weights applied
    client.post(f"/api/interviews/{iv['id']}/consent", json={"microphone": True, "ai_processing": True, "data_retention_ack": True})
    _drive_ws(client, iv["id"], lambda s: "I would use partitioning and a broadcast join because of skew; the trade-off is memory.")
    student_cookies = dict(client.cookies)

    # org A admin sees the candidate, report, transcript and CSV
    client.cookies.clear()
    client.cookies.update(admin_a_cookies)
    dash = client.get("/api/organization").json()
    assert dash["stats"]["interviews_completed"] == 1
    rows = client.get("/api/organization/candidates").json()["items"]
    assert len(rows) == 1 and rows[0]["candidate_name"] == "Student One"
    assert client.get(f"/api/interviews/{iv['id']}/report").status_code == 200
    assert client.get(f"/api/interviews/{iv['id']}/transcript").status_code == 200
    csv_text = client.get("/api/organization/export.csv").text
    assert "Student One" in csv_text
    assert client.patch(f"/api/organization/interviews/{iv['id']}/review", json={"review_status": "shortlisted"}).status_code == 200
    assert client.get(f"/api/organization/compare?ids={iv['id']}").json()["items"][0]["candidate_name"] == "Student One"

    # org B admin sees nothing of org A — even when spoofing X-Org-Id
    client.cookies.clear()
    client.cookies.update(admin_b_cookies)
    assert client.get("/api/organization/candidates").json()["items"] == []
    assert client.get("/api/organization/candidates", headers={"X-Org-Id": org_a["id"]}).status_code == 403
    assert client.get(f"/api/interviews/{iv['id']}/report").status_code == 404
    assert client.patch(f"/api/organization/interviews/{iv['id']}/review", json={"review_status": "rejected"}).status_code == 404
    assert client.get(f"/api/organization/candidates/{rows[0]['candidate_id']}").status_code == 404
    assert "Student One" not in client.get("/api/organization/export.csv").text
    assert client.get(f"/api/organization/compare?ids={iv['id']}").json()["items"] == []

    # the candidate cannot use org endpoints
    client.cookies.clear()
    client.cookies.update(student_cookies)
    assert client.get("/api/organization").status_code == 403
    assert org_b


def test_admin_endpoints_require_super_admin(client):
    register(client, uniq("notadmin"))
    for path in ["/api/admin/command-center", "/api/admin/users", "/api/admin/usage", "/api/admin/questions", "/api/admin/billing"]:
        assert client.get(path).status_code == 403, path


def test_super_admin_command_center(client):
    import asyncio

    from app.db import session_factory
    from app.models import User
    from intervue_security import hash_password

    email = uniq("root")

    async def mk() -> None:
        async with session_factory()() as db:
            db.add(User(email=email, full_name="Root", role="super_admin", password_hash=hash_password("Password!123")))
            await db.commit()

    asyncio.run(mk())
    client.cookies.clear()
    client.post("/api/auth/login", json={"email": email, "password": "Password!123"})
    cc = client.get("/api/admin/command-center").json()
    assert cc["database"] == "ok" and cc["providers"]["ai"]["is_mock"] is True
    assert client.get("/api/admin/usage").status_code == 200
    qs = client.get("/api/admin/questions").json()
    assert len(qs["items"]) > 50


def test_demo_mode_creates_guest_session(client):
    client.cookies.clear()
    iv = client.post("/api/demo/start").json()
    assert iv["is_demo"] and iv["plan"]["role_key"] == "aws_data_engineer" and iv["duration_minutes"] <= 10
    me = client.get("/api/auth/me").json()
    assert me["is_demo"] is True


def test_screen_share_requires_consent_and_compresses(client):
    import io

    from PIL import Image

    register(client, uniq("screen"))
    iv = _create_interview(client)
    buf = io.BytesIO()
    Image.new("RGB", (2560, 1440), "white").save(buf, "PNG")
    files = {"image": ("s.png", buf.getvalue(), "image/png")}
    assert client.post(f"/api/interviews/{iv['id']}/screen-events", data={"event_type": "snapshot"}, files=files).status_code == 403
    client.post(f"/api/interviews/{iv['id']}/consent", json={"microphone": True, "ai_processing": True, "data_retention_ack": True, "screen_share": True})
    r = client.post(f"/api/interviews/{iv['id']}/screen-events", data={"event_type": "snapshot", "reason": "code_review"}, files=files)
    assert r.status_code == 201 and r.json()["width"] == 1280 and r.json()["height"] == 720
    assert client.post(f"/api/interviews/{iv['id']}/screen-events", data={"event_type": "stopped"}).status_code == 201


def test_cost_record_written_after_report(client):
    import asyncio

    from sqlalchemy import select

    from app.db import session_factory
    from app.models import CostRecord, UsageRecord

    register(client, uniq("cost"))
    iv = _create_interview(client, interview_type="behavioral", duration_minutes=30)
    client.post(f"/api/interviews/{iv['id']}/consent", json={"microphone": True, "ai_processing": True, "data_retention_ack": True})
    _drive_ws(
        client,
        iv["id"],
        lambda s: (
            "In my last project our team had a situation where my task was to fix a pipeline; I decided to add retries and as a result we reduced failures by 50%."
        ),
    )

    async def check() -> tuple[int, Any]:
        async with session_factory()() as db:
            n = len((await db.execute(select(UsageRecord).where(UsageRecord.interview_id == uuid.UUID(iv["id"])))).scalars().all())
            cr = (await db.execute(select(CostRecord).where(CostRecord.interview_id == uuid.UUID(iv["id"])))).scalar_one()
            return n, cr

    n, cr = asyncio.run(check())
    assert n > 3 and cr.llm_input_tokens > 0 and cr.estimated_cost_usd == 0.0 and cr.fx_rate > 0
    assert time.time()


def test_retention_purge_removes_expired_interviews(client):
    import asyncio
    from datetime import UTC, datetime, timedelta

    from app.db import session_factory
    from app.models import Interview
    from app.services.orchestrator import purge_expired

    register(client, uniq("retention"))
    iv = _create_interview(client)

    async def age_and_purge() -> tuple[int, Any]:
        async with session_factory()() as db:
            row = await db.get(Interview, uuid.UUID(iv["id"]))
            row.created_at = datetime.now(UTC) - timedelta(days=400)
            await db.commit()
        n = await purge_expired()
        async with session_factory()() as db:
            return n, await db.get(Interview, uuid.UUID(iv["id"]))

    n, gone = asyncio.run(age_and_purge())
    assert n >= 1 and gone is None


def test_background_score_refinement_completes_before_report(client):
    from app.services import orchestrator

    original = orchestrator.engine
    orchestrator.engine = type(original)(original.evaluator.ai, defer_scoring=True)
    try:
        register(client, uniq("refine"))
        iv = _create_interview(client, interview_type="behavioral", duration_minutes=30)
        client.post(f"/api/interviews/{iv['id']}/consent", json={"microphone": True, "ai_processing": True, "data_retention_ack": True})
        _drive_ws(
            client,
            iv["id"],
            lambda s: (
                "In my last role our team had a situation where my task was to fix a flaky pipeline; I decided to add retries and as a result failures dropped by 50%."
            ),
        )
        import asyncio

        from sqlalchemy import select

        from app.db import session_factory
        from app.models import Evaluation

        async def providers() -> set[str]:
            async with session_factory()() as db:
                return {e.provider for e in (await db.execute(select(Evaluation).where(Evaluation.interview_id == uuid.UUID(iv["id"])))).scalars()}

        assert asyncio.run(providers()) == {"mock"}  # every rule-based estimate was replaced by the evaluator's score
        assert client.get(f"/api/interviews/{iv['id']}/report").status_code == 200
    finally:
        orchestrator.engine = original


def test_voice_preview_uses_configured_voice(client):
    r = client.get("/api/voice/preview")
    assert r.status_code == 200
    body = r.json()
    # test settings use browser TTS: the client speaks the sample itself
    assert body["tts"] == "browser" and body["audio"] is None and body["text"]
