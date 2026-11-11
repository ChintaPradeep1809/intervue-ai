"""Seed realistic demo data: `python -m app.seed [--reset]`.

Seeded interviews are produced by running the real engine, evaluator and report pipeline with
scripted candidate answers of varying quality — so dashboards show genuine pipeline output.
All seeded people are fictional and use reserved example domains.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select

from app.db import session_factory
from app.models import (
    Base,
    CandidateProfile,
    CodeExecution,
    CodeSession,
    Interview,
    InterviewTemplate,
    Invite,
    Organization,
    OrganizationMember,
    Plan,
    Question,
    Resume,
    Subscription,
    User,
)
from app.services import orchestrator
from app.services.documents import extract_text
from app.services.interviews import create_interview
from app.services.rag import ingest
from app.services.storage import get_storage, new_key
from intervue_coding import get_sql_problem, grade_sql, run_query
from intervue_engine import QUESTIONS, InterviewState, NextAction
from intervue_eval import CodeFailure, CodeSubmissionSummary
from intervue_security import hash_password

PASSWORDS = {
    "admin@intervue.local": "Admin@12345",
    "college@intervue.local": "College@12345",
    "candidate@intervue.local": "Candidate@12345",
}

PLANS: list[dict[str, Any]] = [
    dict(
        key="free",
        name="Free",
        audience="candidate",
        price_monthly_usd=0,
        price_monthly_inr=0,
        sort_order=1,
        limits={"interviews_per_month": 3, "voice_minutes": 90, "ai_tokens": 300_000, "seats": 1},
        features=["3 practice interviews / month", "Voice interviewer", "Evidence-based report"],
    ),
    dict(
        key="candidate_pro",
        name="Candidate Pro",
        audience="candidate",
        price_monthly_usd=12,
        price_monthly_inr=999,
        sort_order=2,
        limits={"interviews_per_month": 30, "voice_minutes": 1200, "ai_tokens": 4_000_000, "seats": 1},
        features=["30 interviews / month", "All roles & coding rounds", "System design canvas", "Progress history"],
    ),
    dict(
        key="college",
        name="College",
        audience="organization",
        price_monthly_usd=299,
        price_monthly_inr=24_999,
        sort_order=3,
        limits={"interviews_per_month": 500, "voice_minutes": 20_000, "ai_tokens": 60_000_000, "seats": 10},
        features=["500 interviews / month", "Templates & invite links", "Cohort dashboard & CSV export", "Knowledge base"],
    ),
    dict(
        key="enterprise",
        name="Enterprise",
        audience="organization",
        price_monthly_usd=0,
        price_monthly_inr=0,
        sort_order=4,
        limits={"interviews_per_month": None, "voice_minutes": None, "ai_tokens": None, "seats": None},
        features=["Custom volume", "SSO & audit exports", "Custom question banks", "Dedicated support"],
    ),
]

AWS_DE_ROUNDS: list[dict[str, Any]] = [
    {"kind": "introduction", "title": "Introduction", "minutes": 5, "topics": ["introduction"]},
    {"kind": "sql", "title": "SQL", "minutes": 10, "topics": ["sql"], "language": "sql"},
    {"kind": "coding", "title": "Python", "minutes": 10, "topics": ["python"], "language": "python"},
    {"kind": "technical", "title": "AWS", "minutes": 10, "topics": ["aws", "s3", "glue", "athena", "redshift"], "question_count": 2},
    {"kind": "technical", "title": "PySpark", "minutes": 10, "topics": ["pyspark"], "question_count": 2},
    {"kind": "system_design", "title": "System Design", "minutes": 15, "topics": ["system_design"]},
    {"kind": "behavioral", "title": "Behavioral", "minutes": 5, "topics": ["behavioral"]},
]

GLOBAL_TEMPLATES: list[tuple[str, str, str, str, list[dict[str, Any]], str]] = [
    (
        "AWS Data Engineer — 2 Years",
        "aws_data_engineer",
        "junior",
        "medium",
        AWS_DE_ROUNDS,
        "AWS Data Engineer with ~2 years of experience. Must have: SQL, Python, PySpark, AWS (S3, Glue, Athena, Redshift), Airflow. "
        "Nice to have: Kafka, data modeling, data quality frameworks.",
    ),
    (
        "Python Developer — Backend",
        "python_developer",
        "junior",
        "medium",
        [
            {"kind": "introduction", "title": "Introduction", "minutes": 3, "topics": ["introduction"]},
            {"kind": "technical", "title": "Python & APIs", "minutes": 15, "topics": ["python", "api_design", "databases"]},
            {"kind": "coding", "title": "Live coding", "minutes": 15, "topics": ["python"], "language": "python"},
            {"kind": "behavioral", "title": "Behavioral", "minutes": 5, "topics": ["behavioral"]},
        ],
        "",
    ),
    (
        "Software Engineer — New Grad",
        "software_engineer",
        "entry",
        "easy",
        [
            {"kind": "introduction", "title": "Introduction", "minutes": 3, "topics": ["introduction"]},
            {"kind": "coding", "title": "Algorithms", "minutes": 20, "topics": ["algorithms"], "language": "python"},
            {"kind": "technical", "title": "CS fundamentals", "minutes": 12, "topics": ["algorithms", "databases", "api_design"]},
            {"kind": "behavioral", "title": "Behavioral", "minutes": 5, "topics": ["behavioral"]},
        ],
        "",
    ),
    (
        "AI Engineer — LLM Applications",
        "ai_engineer",
        "mid",
        "medium",
        [
            {"kind": "introduction", "title": "Introduction", "minutes": 3, "topics": ["introduction"]},
            {"kind": "technical", "title": "LLMs & ML", "minutes": 15, "topics": ["llm", "machine_learning", "statistics"]},
            {"kind": "coding", "title": "Python coding", "minutes": 12, "topics": ["python"], "language": "python"},
            {"kind": "system_design", "title": "RAG system design", "minutes": 12, "topics": ["system_design"]},
            {"kind": "behavioral", "title": "Behavioral", "minutes": 5, "topics": ["behavioral"]},
        ],
        "",
    ),
    (
        "Forward Deployed Engineer",
        "forward_deployed_engineer",
        "mid",
        "medium",
        [
            {"kind": "introduction", "title": "Introduction", "minutes": 3, "topics": ["introduction"]},
            {"kind": "technical", "title": "Customer scenarios", "minutes": 15, "topics": ["customer_scenarios", "api_design", "llm"]},
            {"kind": "coding", "title": "Integration coding", "minutes": 12, "topics": ["python"], "language": "python"},
            {"kind": "behavioral", "title": "Behavioral", "minutes": 8, "topics": ["behavioral"]},
        ],
        "",
    ),
    (
        "Data Analyst — Entry",
        "data_analyst",
        "entry",
        "easy",
        [
            {"kind": "introduction", "title": "Introduction", "minutes": 3, "topics": ["introduction"]},
            {"kind": "sql", "title": "SQL challenge", "minutes": 12, "topics": ["sql"], "language": "sql"},
            {"kind": "technical", "title": "Analytics & statistics", "minutes": 12, "topics": ["statistics", "data_analysis", "sql"]},
            {"kind": "behavioral", "title": "Behavioral", "minutes": 5, "topics": ["behavioral"]},
        ],
        "",
    ),
    (
        "DevOps Engineer",
        "devops_engineer",
        "mid",
        "medium",
        [
            {"kind": "introduction", "title": "Introduction", "minutes": 3, "topics": ["introduction"]},
            {"kind": "technical", "title": "Containers & CI/CD", "minutes": 18, "topics": ["docker", "kubernetes", "ci_cd", "observability", "linux"]},
            {"kind": "system_design", "title": "Platform design", "minutes": 12, "topics": ["system_design"]},
            {"kind": "behavioral", "title": "Behavioral", "minutes": 5, "topics": ["behavioral"]},
        ],
        "",
    ),
]

CAMPUS_ROUNDS: list[dict[str, Any]] = [
    {"kind": "introduction", "title": "Introduction", "minutes": 3, "topics": ["introduction"]},
    {"kind": "technical", "title": "SQL & PySpark", "minutes": 10, "topics": ["sql", "pyspark"], "question_count": 2},
    {"kind": "sql", "title": "SQL challenge", "minutes": 8, "topics": ["sql"], "language": "sql"},
    {"kind": "technical", "title": "AWS data services", "minutes": 8, "topics": ["aws", "s3", "glue", "athena"], "question_count": 2},
    {"kind": "behavioral", "title": "Behavioral", "minutes": 4, "topics": ["behavioral"]},
]

CANDIDATES = [
    ("Aarav Mehta", 0.92),
    ("Diya Raman", 0.85),
    ("Kabir Singh", 0.78),
    ("Meera Pillai", 0.72),
    ("Rohan Gupta", 0.64),
    ("Sara Thomas", 0.58),
    ("Ishaan Verma", 0.5),
    ("Ananya Rao", 0.42),
    ("Vikram Nair", 0.35),
    ("Priya Iyer", 0.81),
]

RESUME_LINES = [
    "Priya Sharma",
    "Data Engineer | Hyderabad, India | candidate@intervue.local",
    "Summary: Data Engineer with 2 years of experience building batch and streaming pipelines on AWS.",
    "Skills: Python, SQL, PySpark, AWS Glue, Amazon S3, Athena, Redshift, Apache Airflow, Git, Docker.",
    "Experience — Data Engineer, Example Analytics Pvt Ltd (2023–present)",
    "- Built PySpark jobs on AWS Glue processing 200 GB/day of order events into partitioned Parquet on S3.",
    "- Designed Airflow DAGs with retries and SLAs for 40 daily ingestion pipelines.",
    "- Reduced Athena query cost by 35% through partitioning and compaction.",
    "- Loaded curated data into Redshift using COPY with staging tables for upserts.",
    "Education — B.Tech, Computer Science (2022)",
]


def _docx(lines: list[str]) -> bytes:
    import docx

    d = docx.Document()
    for ln in lines:
        d.add_paragraph(ln)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


STAR_PARTS = {
    "context of the situation": "At my previous internship our team had a situation where the nightly pipeline kept missing its SLA.",
    "your specific responsibility": "My task was to find the bottleneck and get the data delivered by 6 AM.",
    "actions you personally took": "I decided to profile each stage, I implemented incremental loads and I worked with the analytics team to agree on priorities.",
    "measurable outcome": "As a result we reduced the runtime by 40% and delivered on time for three months; I learned to communicate trade-offs early.",
    "lessons learned": "I learned to write a short postmortem and prevent repeats with an alert.",
    "how you prioritised": "I had to prioritize ruthlessly and cut scope on the lower-value reports.",
    "how you learned it": "I read the documentation, built a small prototype and asked a mentor to review it.",
}
TEMPLATES = [
    "I would use {kw} here because it handles {name} well in production.",
    "For {name}, I'd rely on {kw}; for example in my last project we processed about 200 GB a day that way.",
    "Another important point is {kw}, which matters for {name}.",
]


def synth_answer(q: dict[str, Any], quality: float, rng: random.Random) -> str:
    concepts = q.get("expected_concepts") or []
    if (q["kind"] in ("primary", "followup") and q["topic"] == "behavioral") or any(c["name"] == "context of the situation" for c in concepts):
        parts = [STAR_PARTS[c["name"]] for c in concepts if c["name"] in STAR_PARTS and rng.random() < quality + 0.1]
        return " ".join(parts) or "I usually try to just get things done and move on."
    if q["topic"] == "introduction":
        base = "I have two years of experience as a data engineer and I currently work on AWS pipelines with Python, SQL and Spark."
        return base + (
            " Recently I built a project that improved data freshness by 30% for our analytics team, which is why I'm excited about this role."
            if quality > 0.5
            else ""
        )
    k = max(0, min(len(concepts), round(len(concepts) * quality + rng.uniform(-0.6, 0.6))))
    chosen = rng.sample(concepts, k) if concepts else []
    parts = [rng.choice(TEMPLATES).format(kw=c["keywords"][0].replace("(", "").strip(), name=c["name"]) for c in chosen]
    if quality > 0.6:
        parts.append("The main trade-off is cost versus latency, so it depends on the data volume and the SLA.")
    if not parts:
        return rng.choice(["I'm not completely sure, I think I would search for it and try a few approaches.", "I don't know this one well."])
    return " ".join(parts)


async def _upsert_plans(db: Any) -> dict[str, Plan]:
    out = {}
    for p in PLANS:
        row = (await db.execute(select(Plan).where(Plan.key == p["key"]))).scalar_one_or_none()
        if row is None:
            row = Plan(**p)
            db.add(row)
        out[p["key"]] = row
    await db.flush()
    return out


async def _upsert_questions(db: Any, sync: bool = False) -> None:
    rows = {q.bank_key: q for q in (await db.execute(select(Question))).scalars()}
    existing = set(rows)
    for q in QUESTIONS:
        row = rows.get(q.id)
        if sync and row is not None and row.organization_id is None:
            # refresh platform questions from code (admin edits to these keys are overwritten)
            row.text, row.topic, row.kind, row.difficulty, row.roles = q.text, q.topic, q.kind, q.difficulty, q.roles
            row.concepts = [c.model_dump() for c in q.concepts]
            row.followups = [f.model_dump() for f in q.followups]
        if q.id not in existing:
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


async def _user(db: Any, email: str, name: str, role: str, password: str | None = None) -> User:
    u = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if u is None:
        u = User(email=email, full_name=name, role=role, password_hash=hash_password(password) if password else None)
        db.add(u)
        await db.flush()
        db.add(CandidateProfile(user_id=u.id, experience_years=2, target_role="aws_data_engineer", onboarding_completed=True))
    return u


async def simulate(iv_id: uuid.UUID, user: User, quality: float, rng: random.Random) -> None:
    await orchestrator.start(iv_id, user)
    for _ in range(40):
        async with session_factory()() as db:
            iv = await db.get(Interview, iv_id)
            st = InterviewState.model_validate(iv.state)
        if st.next_action == NextAction.WAIT_FOR_ANSWER and st.current_question:
            await orchestrator.answer(iv_id, user, synth_answer(st.current_question.model_dump(), quality, rng), "voice")
        elif st.next_action == NextAction.WAIT_FOR_CODE and st.code_state:
            cs = st.code_state
            sp = get_sql_problem(cs.problem_id)
            if sp is None:  # python round: seed data uses SQL rounds only
                await orchestrator.end(iv_id, user, "candidate")
                continue
            query = sp.reference_sql if quality >= 0.6 else "SELECT * FROM customers LIMIT 5"
            cand, ref = run_query(sp.dataset, query), run_query(sp.dataset, sp.reference_sql)
            grade = grade_sql(sp, cand, ref)
            async with session_factory()() as db:
                sess = CodeSession(interview_id=iv_id, problem_id=sp.id, language="sql", is_sql=True, code=query, run_count=2 if quality > 0.7 else 1)
                db.add(sess)
                await db.flush()
                db.add(
                    CodeExecution(
                        code_session_id=sess.id,
                        interview_id=iv_id,
                        kind="submit",
                        language="sql",
                        code=query,
                        status=grade.status,
                        passed=grade.passed,
                        total=grade.total,
                        result={**grade.model_dump(), "problem_title": sp.title},
                        runtime_ms=grade.runtime_ms,
                        backend="sqlite-sandbox",
                    )
                )
                await db.commit()
            summary = CodeSubmissionSummary(
                language="sql",
                code=query,
                problem_id=sp.id,
                problem_title=sp.title,
                passed=grade.passed,
                total=grade.total,
                status="passed" if grade.status == "passed" else "failed",
                expected_features=sp.expected_features,
                failures=[CodeFailure(name=o.name, input="", expected=str(o.expected), actual=str(o.actual)) for o in grade.outcomes if not o.passed],
            )
            await orchestrator.submit_code(iv_id, user, summary, sp.statement)
        else:
            break
    await orchestrator.finalize(iv_id)


async def seed(reset: bool, sync_questions: bool = False) -> None:
    rng = random.Random(7)
    async with session_factory()() as db:
        if reset:
            for table in reversed(Base.metadata.sorted_tables):
                if table.name != "alembic_version":
                    await db.execute(delete(table))
            await db.commit()
        plans = await _upsert_plans(db)
        await _upsert_questions(db, sync_questions)
        admin = await _user(db, "admin@intervue.local", "Platform Admin", "super_admin", PASSWORDS["admin@intervue.local"])
        college_admin = await _user(db, "college@intervue.local", "Dr. Kavya Menon", "organization_admin", PASSWORDS["college@intervue.local"])
        candidate = await _user(db, "candidate@intervue.local", "Priya Sharma", "candidate", PASSWORDS["candidate@intervue.local"])
        org = (await db.execute(select(Organization).where(Organization.name == "Sunrise Institute of Technology"))).scalar_one_or_none()
        if org is None:
            org = Organization(
                name="Sunrise Institute of Technology", slug="sunrise-institute", kind="college", settings={"pass_threshold": 60, "retention_days": 365}
            )
            db.add(org)
            await db.flush()
            db.add(OrganizationMember(organization_id=org.id, user_id=college_admin.id, role="admin"))
            db.add(
                Subscription(plan_id=plans["college"].id, organization_id=org.id, status="active", current_period_end=datetime.now(UTC) + timedelta(days=30))
            )
        if not (await db.execute(select(Resume).where(Resume.user_id == candidate.id))).scalar_one_or_none():
            data = _docx(RESUME_LINES)
            key = new_key(f"resumes/{candidate.id}", ".docx")
            await get_storage().put(key, data, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            db.add(
                Resume(
                    user_id=candidate.id,
                    storage_key=key,
                    filename="priya-sharma-resume.docx",
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    size_bytes=len(data),
                    text=extract_text(data, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                )
            )
        existing_t = {t.name for t in (await db.execute(select(InterviewTemplate))).scalars()}
        for name, role, exp, diff, rounds, jd in GLOBAL_TEMPLATES:
            if name not in existing_t:
                db.add(
                    InterviewTemplate(
                        name=name,
                        role_key=role,
                        experience_level=exp,
                        difficulty=diff,
                        interview_type="full",
                        rounds=rounds,
                        topics=sorted({t for r in rounds for t in r["topics"]}),
                        duration_minutes=sum(r["minutes"] for r in rounds),
                        jd_text=jd,
                    )
                )
        campus = (await db.execute(select(InterviewTemplate).where(InterviewTemplate.name == "Campus Placement — Data Engineering 2026"))).scalar_one_or_none()
        if campus is None:
            campus = InterviewTemplate(
                organization_id=org.id,
                name="Campus Placement — Data Engineering 2026",
                role_key="aws_data_engineer",
                experience_level="entry",
                difficulty="medium",
                interview_type="full",
                rounds=CAMPUS_ROUNDS,
                topics=["sql", "pyspark", "aws", "s3", "glue", "athena"],
                duration_minutes=sum(r["minutes"] for r in CAMPUS_ROUNDS),
                created_by=college_admin.id,
                jd_text="Graduate Data Engineer: SQL, Python, PySpark, AWS (S3, Glue, Athena). Strong fundamentals and communication.",
            )
            db.add(campus)
            await db.flush()
            db.add(
                Invite(
                    organization_id=org.id,
                    template_id=campus.id,
                    token="sunrise-campus-2026",
                    label="Campus drive — batch 2026",
                    max_uses=500,
                    expires_at=datetime.now(UTC) + timedelta(days=60),
                    created_by=college_admin.id,
                )
            )
            await ingest(
                db,
                org.id,
                "Placement interview guidelines",
                "guidelines",
                "",
                "Sunrise placement guidelines.\n\nFocus on SQL fundamentals: joins, aggregation and window functions.\n\n"
                "Every candidate should be asked about data quality checks and partitioning on S3.\n\n"
                "Communication matters: candidates must explain trade-offs clearly.",
            )
        await db.commit()

        seeded = (await db.execute(select(Interview).where(Interview.organization_id == org.id))).scalars().first()
        cand_users = []
        if seeded is None:
            for i, (name, _) in enumerate(CANDIDATES):
                email = f"{name.split()[0].lower()}.{name.split()[1].lower()}@student.example.edu"
                u = await _user(db, email, name, "candidate", f"Student@{1000 + i}")
                db.add(OrganizationMember(organization_id=org.id, user_id=u.id, role="candidate"))
                cand_users.append(u)
            await db.commit()
            campus_id = campus.id
            ivs = []
            for u in cand_users:
                iv = await create_interview(
                    db,
                    u,
                    role_key="aws_data_engineer",
                    interview_type="full",
                    duration_minutes=campus.duration_minutes,
                    difficulty="medium",
                    template=campus,
                    organization_id=org.id,
                    title=f"{campus.name} — {org.name}",
                )
                iv.consent = {"accepted": True, "microphone": True, "ai_processing": True, "data_retention_ack": True, "seeded": True}
                ivs.append(iv.id)
            await db.commit()
        else:
            campus_id = campus.id
            ivs = []
        candidate_iv = None
        if not (await db.execute(select(Interview).where(Interview.candidate_id == candidate.id))).scalars().first():
            resume = (await db.execute(select(Resume).where(Resume.user_id == candidate.id))).scalar_one()
            civ = await create_interview(
                db, candidate, role_key="aws_data_engineer", interview_type="technical", duration_minutes=30, difficulty="medium", resume=resume
            )
            civ.consent = {"accepted": True, "microphone": True, "ai_processing": True, "data_retention_ack": True, "seeded": True}
            candidate_iv = civ.id
            await db.commit()
        admin_id = admin.id

    for i, iv_id in enumerate(ivs):
        async with session_factory()() as db:
            iv = await db.get(Interview, iv_id)
            u = await db.get(User, iv.candidate_id)
        await simulate(iv_id, u, CANDIDATES[i][1], rng)
        async with session_factory()() as db:  # spread completions over the last two weeks
            iv = await db.get(Interview, iv_id)
            shift = timedelta(days=rng.randint(0, 13), hours=rng.randint(0, 8))
            for f in ("created_at", "started_at", "completed_at"):
                if getattr(iv, f):
                    setattr(iv, f, getattr(iv, f) - shift)
            if (iv.overall_score or 0) >= 75:
                iv.review_status = "shortlisted"
            await db.commit()
        print(f"  seeded interview {i + 1}/{len(ivs)} -> score {iv.overall_score}")
    if candidate_iv:
        async with session_factory()() as db:
            u = await db.get(User, (await db.get(Interview, candidate_iv)).candidate_id)
        await simulate(candidate_iv, u, 0.7, rng)
        print("  seeded candidate practice interview")
    print(f"Seed complete. Admin id {admin_id}; campus template {campus_id}. See DEMO_CREDENTIALS.md")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="delete all data first")
    parser.add_argument("--sync-questions", action="store_true", help="refresh platform questions from the code bank")
    args = parser.parse_args()
    if sys.platform == "win32":
        asyncio.run(seed(args.reset, args.sync_questions), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(seed(args.reset, args.sync_questions))


if __name__ == "__main__":
    main()
