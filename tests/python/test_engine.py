"""Interview state machine, planning, analysis, follow-ups and evaluation."""

import time

import pytest

from intervue_ai import AIClient, MockAIProvider
from intervue_engine import (
    QUESTIONS,
    TRANSITIONS,
    EngineContext,
    EngineError,
    InterviewEngine,
    InterviewState,
    InvalidTransition,
    NextAction,
    Phase,
    build_plan,
    extract_skills,
    verify_skills,
)
from intervue_engine.analysis import analyze
from intervue_engine.schemas import SkillEvidence
from intervue_engine.states import assert_transition
from intervue_eval import AnswerScore, CodeSubmissionSummary, Evidence, ExpectedConcept, verify_evidence
from intervue_eval.report import AnswerRecord, TimeStats, build_report
from intervue_eval.scoring import EvaluationProvider

RESUME = "Priya Sharma\nData Engineer with 2 years of experience in Python, SQL and PySpark on AWS Glue and Athena."


@pytest.fixture
def ai():
    return AIClient([MockAIProvider()])


def test_transition_table_is_closed():
    for src, dsts in TRANSITIONS.items():
        assert Phase.FINAL_EVALUATION in dsts or src in (Phase.FINAL_EVALUATION, Phase.COMPLETED)
    assert TRANSITIONS[Phase.COMPLETED] == set()
    with pytest.raises(InvalidTransition):
        assert_transition(Phase.COMPLETED, Phase.INTRODUCTION)
    with pytest.raises(InvalidTransition):
        assert_transition(Phase.FINAL_EVALUATION, Phase.CODING)


def test_skill_extraction_and_hallucination_guard():
    names = {s.name for s in extract_skills(RESUME)}
    assert {"Python", "SQL", "PySpark", "AWS Glue", "Amazon Athena"} <= names
    assert "Apache Kafka" not in names
    claimed = [SkillEvidence(name="Apache Kafka", topic="kafka", evidence="streamed events with Kafka"), SkillEvidence(name="SQL", topic="sql", evidence="SQL")]
    assert [s.name for s in verify_skills(claimed, RESUME)] == ["SQL"]


async def test_analysis_and_plan(ai):
    analysis, _ = await analyze(ai, RESUME, "Need Kafka, Airflow and Redshift experience.", "aws_data_engineer", 2)
    assert analysis.experience_level == "junior" and analysis.years_experience == 2
    assert "Apache Kafka" in analysis.skill_gaps
    for minutes in (30, 45, 60):
        plan = build_plan("aws_data_engineer", "full", minutes, "medium", analysis)
        assert abs(plan.duration_minutes - minutes) <= 2
        kinds = [r.kind for r in plan.rounds]
        assert kinds[0] == "introduction" and "behavioral" in kinds and ("coding" in kinds or "sql" in kinds)
        assert round(sum(w.weight for w in plan.skill_weights), 2) == pytest.approx(1.0, abs=0.02)
    templated = build_plan("aws_data_engineer", "full", 45, "medium", analysis, [{"kind": "technical", "minutes": 10, "topics": ["sql"], "question_count": 2}])
    assert len(templated.rounds) == 1 and templated.rounds[0].question_count == 2


GOOD = {
    "introduction": "I have two years of experience building AWS data pipelines; I'm interested because I enjoy reliable data platforms and the role fits my skills.",
}


def good_answer(q) -> str:
    if q.topic in GOOD:
        return GOOD[q.topic]
    words = [c["keywords"][0] for c in q.expected_concepts]
    return "I would use " + ", ".join(words) + " because it handles the trade-off between cost and latency, for example on 200 GB per day."


async def test_full_interview_runs_to_completion_without_repeats(ai):
    analysis, _ = await analyze(ai, RESUME, "", "aws_data_engineer", 2)
    plan = build_plan("aws_data_engineer", "full", 45, "medium", analysis)
    eng = InterviewEngine(ai, max_followups=2)
    st = InterviewState(interview_id="i", candidate_id="c", role="aws_data_engineer")
    now = time.time()
    ctx = lambda: EngineContext(plan=plan, bank=QUESTIONS, now=now, analysis=analysis, candidate_name="Priya")  # noqa: E731
    out = await eng.start(st, ctx())
    assert out.utterances[0].kind == "greeting" and st.phase == Phase.INTRODUCTION
    asked_primary: list[str] = []
    followups_per_root: dict[str, int] = {}
    for _ in range(80):
        if st.next_action == NextAction.WAIT_FOR_ANSWER:
            q = st.current_question
            if q.kind in ("primary", "design"):
                asked_primary.append(q.qid)
            if q.kind == "followup":
                followups_per_root[q.parent_qid] = followups_per_root.get(q.parent_qid, 0) + 1
            now += 30
            await eng.handle_answer(st, ctx(), good_answer(q))
        elif st.next_action == NextAction.WAIT_FOR_CODE:
            cs = st.code_state
            now += 120
            sub = CodeSubmissionSummary(
                language=cs.language, code="def f(x):\n    return x\n", problem_id=cs.problem_id, problem_title="t", passed=2, total=3, status="failed"
            )
            out = await eng.handle_code_submission(st, ctx(), sub, "statement")
            assert st.phase == Phase.CODE_REVIEW and "hidden test" in out.utterances[0].text
        else:
            break
    assert st.phase == Phase.FINAL_EVALUATION
    assert len(asked_primary) == len(set(asked_primary)), "questions must not repeat"
    assert all(n <= 2 for n in followups_per_root.values())
    assert st.rounds_completed == len(plan.rounds)
    eng.mark_completed(st)
    assert st.phase == Phase.COMPLETED


async def test_repeat_request_is_not_scored_and_dont_know_skips_followup(ai):
    plan = build_plan("aws_data_engineer", "technical", 30, "medium", None)
    eng = InterviewEngine(ai)
    st = InterviewState(interview_id="i", candidate_id="c", role="aws_data_engineer")
    ctx = EngineContext(plan=plan, bank=QUESTIONS, now=time.time())
    await eng.start(st, ctx)
    q = st.current_question.text
    out = await eng.handle_answer(st, ctx, "Sorry, could you repeat that?")
    assert not out.scored and q in out.utterances[0].text
    out = await eng.handle_answer(st, ctx, "I don't know")
    assert out.scored[0].score.score < 15
    assert st.current_question.kind == "primary"  # moved on, no follow-up
    with pytest.raises(EngineError):
        await eng.handle_code_submission(
            st, ctx, CodeSubmissionSummary(language="python", code="", problem_id="x", problem_title="x", passed=0, total=1, status="failed"), ""
        )


async def test_difficulty_adapts(ai):
    plan = build_plan("aws_data_engineer", "technical", 60, "medium", None)
    eng = InterviewEngine(ai, max_followups=0)
    st = InterviewState(interview_id="i", candidate_id="c", role="aws_data_engineer")
    now = time.time()
    await eng.start(st, EngineContext(plan=plan, bank=QUESTIONS, now=now))
    await eng.handle_answer(st, EngineContext(plan=plan, bank=QUESTIONS, now=now), GOOD["introduction"])
    start = st.difficulty
    await eng.handle_answer(st, EngineContext(plan=plan, bank=QUESTIONS, now=now + 30), good_answer(st.current_question))
    assert st.difficulty == min(3, start + 1)


async def test_followup_types_follow_answer_quality(ai):
    from intervue_engine.followup import rule_followup

    base = {
        "covered": ["window function"],
        "missing": [],
        "used_followups": [],
        "round_kind": "technical",
        "difficulty": 2,
        "time_ok": True,
        "bank_followups": [
            {"type": "edge_case", "trigger": "mentioned:window function", "text": "What about ties?"},
            {"type": "optimization", "trigger": "any", "text": "Billion rows?"},
            {"type": "clarification", "trigger": "missing:window function", "text": "Single pass?"},
        ],
    }
    assert rule_followup({**base, "score": 85}).type == "optimization"
    assert rule_followup({**base, "score": 85}).difficulty == "hard"
    assert rule_followup({**base, "score": 65}).type == "edge_case"
    weak = rule_followup({**base, "score": 30, "covered": [], "missing": ["window function"]})
    assert weak.type == "clarification" and weak.difficulty == "easy"
    assert not rule_followup({**base, "score": 85, "time_ok": False}).should_follow_up
    assert not rule_followup({**base, "score": 85, "followups_for_current": 2, "max_followups": 2}).should_follow_up


def test_evidence_verification_drops_fabricated_quotes():
    score = AnswerScore(
        score=80,
        categories=[],
        covered_concepts=[],
        missing_concepts=[],
        strengths=[],
        weaknesses=[],
        summary="",
        confidence=0.8,
        evidence=[
            Evidence(source="transcript", quote="I partitioned by date", observation="ok", polarity="positive"),
            Evidence(source="transcript", quote="I have used Kafka for five years", observation="invented", polarity="positive"),
            Evidence(source="transcript", kind="absence", observation="No mention of skew", polarity="negative"),
        ],
    )
    v = verify_evidence(score, {"transcript": "Well, I  partitioned by DATE and used Glue."})
    assert [e.observation for e in v.evidence] == ["ok", "No mention of skew"]
    assert v.confidence < 0.8


async def test_code_correctness_is_measured_not_judged(ai):
    ev = EvaluationProvider(ai)
    sub = CodeSubmissionSummary(language="python", code="def f():\n    return 1\n", problem_id="p", problem_title="P", passed=1, total=4, status="failed")
    score, _ = await ev.score_code(sub, "stmt")
    tc = next(c.score for c in score.categories if c.category == "technical_correctness")
    assert tc == 25


async def test_report_aggregation(ai):
    def rec(topic, s, kind="primary", rk="technical", missing=()):
        return AnswerRecord(
            question="q",
            topic=topic,
            topic_label=topic.upper(),
            round_kind=rk,
            kind=kind,
            score=AnswerScore(
                score=s, categories=[], covered_concepts=[], missing_concepts=list(missing), evidence=[], strengths=[], weaknesses=[], summary="s"
            ),
        )

    recs = [
        rec("sql", 90),
        rec("pyspark", 40, missing=["data skew", "broadcast join"]),
        rec("pyspark", 50, missing=["data skew"]),
        rec("behavioral", 70, rk="behavioral"),
    ]
    report, _ = await build_report(
        recs,
        TimeStats(planned_minutes=30, actual_minutes=28, rounds_planned=3, rounds_completed=3),
        {"sql": 0.5, "pyspark": 0.3, "behavioral": 0.2},
        {},
        [],
        ai,
    )
    assert report.narrative.strongest_area == "Your strongest area is SQL."
    assert report.narrative.main_weakness == "Your main weakness is PYSPARK."
    assert report.recommended_topics[0] == "data skew"
    assert "PYSPARK" in report.weak_areas and report.role_readiness in ("developing", "nearly_ready")
    assert any(c.category == "time_management" for c in report.category_scores)
    assert ExpectedConcept(name="x", keywords=["y"])


async def test_deferred_scoring_routes_on_rule_score_and_carries_refinement_payload(ai):
    plan = build_plan("aws_data_engineer", "technical", 30, "medium", None)
    eng = InterviewEngine(ai, defer_scoring=True)
    st = InterviewState(interview_id="i", candidate_id="c", role="aws_data_engineer")
    ctx = EngineContext(plan=plan, bank=QUESTIONS, now=time.time())
    await eng.start(st, ctx)
    out = await eng.handle_answer(st, ctx, GOOD["introduction"])
    sa = out.scored[0]
    assert sa.provider == "rule-based" and sa.refine is not None and sa.refine["kind"] == "answer"
    payload = {k: v for k, v in sa.refine.items() if k != "kind"}
    refined, _ = await eng.evaluator.score_answer(**payload)
    assert 0 <= refined.score <= 100


def test_concept_names_are_pinned_to_expected_list():
    from intervue_eval.scoring import normalize_concepts

    expected = [ExpectedConcept(name="salting", keywords=["salt"]), ExpectedConcept(name="broadcast join", keywords=["broadcast"])]
    base = AnswerScore(
        score=70,
        categories=[],
        evidence=[],
        strengths=[],
        weaknesses=[],
        summary="",
        missing_concepts=["something invented"],
        covered_concepts=["Salting the hot key spreads load"],
    )
    fixed = normalize_concepts(base, expected, "I would salt the hot key")
    assert fixed.covered_concepts == ["salting"] and fixed.missing_concepts == ["broadcast join"]
    exact = normalize_concepts(base.model_copy(update={"covered_concepts": ["Broadcast Join"]}), expected, "")
    assert exact.covered_concepts == ["broadcast join"] and exact.missing_concepts == ["salting"]
