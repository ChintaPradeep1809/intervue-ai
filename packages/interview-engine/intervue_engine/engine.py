"""InterviewEngine: drives the state machine.

The engine mutates an `InterviewState` and returns an `EngineOutput` describing what should be
said, which events to broadcast and which records to persist. It performs AI calls (scoring,
follow-ups, personalisation) but no I/O of its own, so it is fully unit-testable.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from intervue_ai import AIClient, AIRequest, ToolSpec
from intervue_coding import CodingProblem, SqlProblem, pick_problem, pick_sql_problem, public_view, sql_public_view
from intervue_engine.followup import FollowUpAgent
from intervue_engine.question_bank import BankQuestion
from intervue_engine.schemas import (
    LEVEL,
    AskedQuestion,
    CodeReviewQuestion,
    CodeState,
    InterviewPlan,
    InterviewState,
    NextAction,
    PersonalizedQuestion,
    Phase,
    PlanRound,
    ResumeAnalysis,
    ScoreEntry,
)
from intervue_engine.states import ROUND_PHASE, assert_transition
from intervue_engine.taxonomy import topic_label
from intervue_eval import AnswerScore, CodeSubmissionSummary, EvaluationProvider, ExpectedConcept
from intervue_eval.text import DONT_KNOW

ACKS = ["Okay.", "Got it.", "Thanks.", "Understood.", "Alright.", "Thank you."]
REPEAT = re.compile(r"\b(repeat|say that again|come again|didn'?t (catch|hear)|pardon|one more time)\b", re.I)
WRAP_UP_SECONDS = 45

FOLLOWUP_CONCEPTS: dict[str, list[tuple[str, str]]] = {
    "optimization": [
        ("performance tuning", "index|partition|cache|pre-aggregat|parallel|optimi|explain|broadcast|batch|incremental"),
        ("cost/latency trade-offs", "trade-off|tradeoff|cost|latency|memory|storage|throughput"),
    ],
    "edge_case": [
        ("edge case reasoning", "edge case|null|empty|duplicate|tie|late|skew|fail|missing|overflow|timeout"),
        ("mitigation", "handle|check|validat|fallback|retry|dedup|guard|alert|default"),
    ],
    "challenge": [
        ("justification", "because|reason|trade-off|instead|compared|since|so that"),
        ("alternatives considered", "alternative|instead|option|could also|another approach|versus|vs"),
    ],
    "architecture": [
        ("components & data flow", "service|queue|storage|database|pipeline|stream|api|layer"),
        ("reliability", "retry|idempoten|checkpoint|monitor|alert|replay|backfill|dead letter|dlq"),
    ],
    "behavioral": [("outcome", "result|outcome|improved|reduced|delivered|impact|%"), ("reflection", "learned|differently|next time|would change|lesson")],
    "clarification": [("specific detail", "for example|e.g.|specifically|step|first|then|because")],
}


@dataclass
class Utterance:
    text: str
    kind: str  # greeting | question | followup | transition | ack | closing | info


@dataclass
class ScoredAnswer:
    question: AskedQuestion
    answer: str
    score: AnswerScore
    provider: str = ""
    fallback_used: bool = False
    # When set, the score is a fast deterministic estimate; the caller refines it with the LLM in the
    # background using these inputs (EvaluationProvider.score_answer / score_code kwargs).
    refine: dict[str, Any] | None = None


@dataclass
class EngineOutput:
    utterances: list[Utterance] = field(default_factory=list)
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    scored: list[ScoredAnswer] = field(default_factory=list)
    asked: list[AskedQuestion] = field(default_factory=list)
    round_completed: list[str] = field(default_factory=list)
    finished: bool = False

    def say(self, text: str, kind: str) -> None:
        self.utterances.append(Utterance(text=text, kind=kind))


@dataclass
class EngineContext:
    plan: InterviewPlan
    bank: list[BankQuestion]
    now: float
    analysis: ResumeAnalysis | None = None
    candidate_name: str | None = None
    design_text: str = ""
    tools: list[ToolSpec] = field(default_factory=list)
    allow_personalization: bool = True


class EngineError(Exception):
    pass


class InterviewEngine:
    def __init__(self, ai: AIClient, max_followups: int = 2, fast_ai: AIClient | None = None, defer_scoring: bool = False) -> None:
        """`ai` scores answers; `fast_ai` (defaults to `ai`) handles latency-sensitive turns: follow-ups,
        personalisation and code-review questions. With `defer_scoring`, answers are routed on an instant
        deterministic score and the LLM score is computed off the critical path by the caller."""
        self.ai = fast_ai or ai
        self.evaluator = EvaluationProvider(ai)
        self.followups = FollowUpAgent(self.ai, max_followups=max_followups)
        self.defer_scoring = defer_scoring

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _round(state: InterviewState, ctx: EngineContext) -> PlanRound:
        return ctx.plan.rounds[state.round_index]

    @staticmethod
    def _move(state: InterviewState, phase: Phase) -> None:
        if state.phase != phase:
            assert_transition(state.phase, phase)
            state.phase = phase

    def _ack(self, state: InterviewState) -> str:
        state.utterance_count += 1
        return ACKS[state.utterance_count % len(ACKS)]

    @staticmethod
    def _global_left(state: InterviewState, now: float) -> float:
        return state.time_remaining(now) if state.deadline_at else 1e9  # type: ignore[return-value]

    def _round_left(self, state: InterviewState, ctx: EngineContext) -> float:
        r = self._round(state, ctx)
        return r.minutes * 60 - (ctx.now - (state.round_started_at or ctx.now))

    @staticmethod
    def _bank_by_id(ctx: EngineContext) -> dict[str, BankQuestion]:
        return {q.id: q for q in ctx.bank}

    # ------------------------------------------------------------------ lifecycle
    async def start(self, state: InterviewState, ctx: EngineContext) -> EngineOutput:
        if state.phase != Phase.INTERVIEW_SETUP:
            raise EngineError("Interview already started")
        out = EngineOutput()
        state.started_at = ctx.now
        state.deadline_at = ctx.now + ctx.plan.duration_minutes * 60
        state.difficulty = LEVEL.get(ctx.plan.difficulty, 2)
        first = (ctx.candidate_name or "").split(" ")[0]
        titles = [r.title for r in ctx.plan.rounds if r.kind != "introduction"]
        sections = ", ".join(titles[:-1]) + (f" and {titles[-1]}" if len(titles) > 1 else (titles[0] if titles else ""))
        out.say(
            f"Hi{' ' + first if first else ''}, thanks for joining. I'll be your interviewer for this "
            f"{ctx.plan.duration_minutes}-minute {ctx.plan.role_title} interview. We'll cover {sections}. "
            "Please think out loud — I'm interested in your reasoning, not just the final answer. "
            "If you'd like me to repeat a question, just ask.",
            "greeting",
        )
        out.events.append(("INTERVIEW_STARTED", {"deadline_at": state.deadline_at, "rounds": [r.model_dump() for r in ctx.plan.rounds]}))
        await self._enter_round(state, ctx, 0, out)
        return out

    async def _enter_round(self, state: InterviewState, ctx: EngineContext, idx: int, out: EngineOutput) -> None:
        if idx >= len(ctx.plan.rounds):
            await self._finish(state, ctx, out, "completed")
            return
        if self._global_left(state, ctx.now) < WRAP_UP_SECONDS:
            await self._finish(state, ctx, out, "time")
            return
        r = ctx.plan.rounds[idx]
        state.round_index = idx
        state.current_round = r.id
        state.question_index = 0
        state.followups_for_current = 0
        state.round_started_at = ctx.now
        state.code_state = None
        self._move(state, ROUND_PHASE[r.kind])
        out.events.append(("ROUND_STARTED", {"round": r.model_dump(), "index": idx}))
        if idx > 0:
            out.say(f"Let's move on to the {r.title} section.", "transition")
        if r.kind in ("coding", "sql"):
            self._start_coding(state, ctx, out)
        else:
            if not await self._ask_next_primary(state, ctx, out):
                await self._complete_round(state, ctx, out)

    def _select(self, state: InterviewState, ctx: EngineContext, r: PlanRound) -> BankQuestion | None:
        kind = {"technical": "technical", "behavioral": "behavioral", "introduction": "introduction", "system_design": "system_design"}[r.kind]
        role = ctx.plan.role_key
        pool = [q for q in ctx.bank if q.kind == kind and q.id not in state.asked_question_ids and (not q.roles or role in q.roles or kind == "technical")]
        if kind == "system_design":
            role_pool = [q for q in pool if role in q.roles]
            pool = role_pool or pool
        if not pool:
            return None
        if kind in ("technical",):
            asked_topics = [q.topic for q in ctx.bank if q.id in state.asked_question_ids]
            priority = set(ctx.analysis.priority_topics) if ctx.analysis else set()
            order = {t: i for i, t in enumerate(r.topics)}
            topics = [t for t in r.topics if any(q.topic == t for q in pool)]
            if not topics:
                return None
            topic = min(topics, key=lambda t: (asked_topics.count(t), 0 if t in priority else 1, order[t]))
            pool = [q for q in pool if q.topic == topic]
        return min(pool, key=lambda q: (abs(q.difficulty - state.difficulty), q.id))

    async def _ask_next_primary(self, state: InterviewState, ctx: EngineContext, out: EngineOutput) -> bool:
        r = self._round(state, ctx)
        q = self._select(state, ctx, r)
        if q is None:
            return False
        text = q.text
        if (
            ctx.allow_personalization
            and ctx.analysis
            and r.kind == "technical"
            and q.topic not in state.personalized_topics
            and len(state.personalized_topics) < 2
        ):
            match = next((s for s in ctx.analysis.skills if s.topic == q.topic), None)
            if match:
                res = await self.ai.run(
                    AIRequest(
                        task="personalize_question",
                        schema=PersonalizedQuestion,
                        system="Rephrase the interview question so it naturally references the candidate's resume skill. "
                        "Only reference the skill given; do not add facts. Keep the technical substance identical. One or two sentences.",
                        prompt=f'Resume skill (verified): {match.name} — resume excerpt: "{match.evidence}"\nQuestion: {q.text}',
                        context={"question": q.text, "matching_skill": match.name},
                        effort="low",
                        max_tokens=600,
                    )
                )
                p = res.output
                verified = {s.name.lower() for s in ctx.analysis.skills}
                if p.referenced_skill is None or p.referenced_skill.lower() in verified:
                    text = p.text
                state.personalized_topics.append(q.topic)
        aq = AskedQuestion(
            qid=q.id,
            round_id=r.id,
            topic=q.topic,
            text=text,
            difficulty=q.difficulty,
            kind="design" if r.kind == "system_design" else "primary",
            expected_concepts=[c.model_dump() for c in q.concepts],
            asked_at=ctx.now,
        )
        state.current_question = aq
        state.asked_question_ids.append(q.id)
        state.question_index += 1
        state.followups_for_current = 0
        self._move(state, ROUND_PHASE[r.kind])
        state.next_action = NextAction.WAIT_FOR_ANSWER
        out.asked.append(aq)
        prefix = "" if state.question_index == 1 and r.kind != "behavioral" else ("Next question. " if state.question_index > 1 else "")
        if r.kind == "system_design":
            prefix = "Use the design canvas to sketch your architecture as you talk me through it. "
        out.say(prefix + text, "question")
        out.events.append(("QUESTION_STARTED", {"question": aq.model_dump(), "round_id": r.id, "index": state.question_index, "of": r.question_count}))
        return True

    def _start_coding(self, state: InterviewState, ctx: EngineContext, out: EngineOutput) -> None:
        r = self._round(state, ctx)
        is_sql = r.kind == "sql" or r.language == "sql"
        exclude = set(state.asked_question_ids)
        problem: CodingProblem | SqlProblem
        if is_sql:
            problem = pick_sql_problem(state.difficulty, exclude)
            view = sql_public_view(problem)
            language = "sql"
            starter = view["starter"]["sql"]
        else:
            problem = pick_problem(ctx.plan.role_key, state.difficulty, exclude)
            view = public_view(problem)
            language = r.language or "python"
            starter = problem.starter.get(language, problem.starter["python"])
        state.code_state = CodeState(problem_id=problem.id, language=language, is_sql=is_sql, code=starter)
        aq = AskedQuestion(
            qid=problem.id,
            round_id=r.id,
            topic=r.topics[0] if r.topics else ("sql" if is_sql else "python"),
            text=f"{problem.title}: {problem.statement}",
            difficulty=problem.difficulty,
            kind="coding",
            asked_at=ctx.now,
        )
        state.current_question = aq
        state.asked_question_ids.append(problem.id)
        state.question_index = 1
        state.next_action = NextAction.WAIT_FOR_CODE
        out.asked.append(aq)
        what = "write a single SQL query" if is_sql else f"write your solution in {language.title() if language != 'javascript' else 'JavaScript'}"
        out.say(
            f'For this round, please solve "{problem.title}". The full problem is on your screen. '
            f"{what[0].upper() + what[1:]} in the editor, run it as often as you like, and submit when you're ready. "
            "Feel free to talk through your approach while you work.",
            "question",
        )
        out.events.append(("CODING_STARTED", {"problem": view, "language": language, "is_sql": is_sql, "round_id": r.id}))

    # ------------------------------------------------------------------ candidate input
    async def handle_answer(self, state: InterviewState, ctx: EngineContext, answer: str) -> EngineOutput:
        out = EngineOutput()
        if state.phase in (Phase.FINAL_EVALUATION, Phase.COMPLETED):
            raise EngineError("Interview has ended")
        if state.next_action != NextAction.WAIT_FOR_ANSWER or state.current_question is None:
            raise EngineError("Not expecting a spoken answer right now")
        answer = answer.strip()
        q = state.current_question
        if REPEAT.search(answer) and len(answer.split()) <= 14:
            out.say(f"Sure. {q.text}", "question")
            return out
        if self._global_left(state, ctx.now) <= 0:
            await self._finish(state, ctx, out, "time")
            return out

        r = self._round(state, ctx)
        concepts = [ExpectedConcept.model_validate(c) for c in q.expected_concepts]
        score_kwargs: dict[str, Any] = {
            "question": q.text,
            "answer": answer,
            "topic": q.topic,
            "topic_label": topic_label(q.topic),
            "round_kind": r.kind,
            "expected_concepts": concepts,
            "design_text": ctx.design_text if r.kind == "system_design" else "",
            "recent_context": state.context_summary,
        }
        if self.defer_scoring:
            score = self.evaluator.quick_score_answer(**{k: v for k, v in score_kwargs.items() if k not in ("question", "recent_context")})
            out.scored.append(ScoredAnswer(question=q, answer=answer, score=score, provider="rule-based", refine={"kind": "answer", **score_kwargs}))
        else:
            score, res = await self.evaluator.score_answer(**score_kwargs)
            out.scored.append(ScoredAnswer(question=q, answer=answer, score=score, provider=res.provider, fallback_used=res.fallback_used))
        state.score_history.append(ScoreEntry(qid=q.qid, topic=q.topic, kind=q.kind, score=score.score))
        for s in score.strengths[:1]:
            if s not in state.strengths:
                state.strengths.append(s)
        for w in score.weaknesses[:2]:
            if w not in state.weaknesses:
                state.weaknesses.append(w)
        state.context_summary = " | ".join((state.context_summary.split(" | ") + [f"{topic_label(q.topic)} {q.kind}: {score.score}"])[-6:]).strip(" |")
        if q.kind == "primary":
            if score.score >= 80:
                state.difficulty = min(3, state.difficulty + 1)
            elif score.score < 45:
                state.difficulty = max(1, state.difficulty - 1)

        root_id = q.parent_qid or q.qid
        bank_q = self._bank_by_id(ctx).get(root_id)
        bank_followups = [f.model_dump() for f in bank_q.followups] if bank_q else []
        time_ok = self._round_left(state, ctx) > 75 and self._global_left(state, ctx.now) > 120
        decision, _ = await self.followups.decide(
            question=q.text,
            answer=answer,
            score=score.score,
            covered=score.covered_concepts,
            missing=score.missing_concepts,
            expected_concepts=q.expected_concepts,
            bank_followups=bank_followups,
            used_followups=state.used_followups,
            followups_for_current=state.followups_for_current,
            round_kind=r.kind,
            topic_label=topic_label(q.topic),
            difficulty=state.difficulty,
            time_ok=time_ok,
            dont_know=bool(DONT_KNOW.search(answer)) and len(answer.split()) < 25,
            recent_context=state.context_summary,
            objective=f"Assess {ctx.plan.role_title} candidate on {topic_label(q.topic)}",
            tools=ctx.tools,
        )
        if decision.should_follow_up and decision.question:
            fq = AskedQuestion(
                qid=f"{root_id}#f{uuid.uuid4().hex[:6]}",
                round_id=r.id,
                topic=q.topic,
                text=decision.question,
                difficulty=LEVEL.get(decision.difficulty, state.difficulty),
                kind="followup",
                followup_type=decision.type,
                parent_qid=root_id,
                expected_concepts=self._followup_concepts(bank_q, decision.expected_concepts, q, decision.type, score.missing_concepts),
                asked_at=ctx.now,
            )
            state.current_question = fq
            state.followups_for_current += 1
            state.used_followups.append(decision.question)
            self._move(state, Phase.FOLLOW_UP)
            state.next_action = NextAction.WAIT_FOR_ANSWER
            out.asked.append(fq)
            out.say(f"{self._ack(state)} {decision.question}", "followup")
            out.events.append(("FOLLOWUP_GENERATED", {"question": fq.model_dump(), "type": decision.type}))
            return out

        out.say(self._ack(state) if not DONT_KNOW.search(answer) else "No problem.", "ack")
        await self._advance(state, ctx, out)
        return out

    @staticmethod
    def _followup_concepts(bank_q: BankQuestion | None, names: list[str], q: AskedQuestion, ftype: str, missing: list[str]) -> list[dict[str, Any]]:
        """Concepts a follow-up answer is scored against. Clarifications target what was missing;
        other follow-ups probe a new angle, so the base question's concepts don't apply."""
        if bank_q and names:
            selected = [c.model_dump() for c in bank_q.concepts if c.name in names]
            if selected and ftype == "clarification":
                return selected
        if ftype == "clarification":
            base = bank_q.concepts if bank_q else []
            selected = [c.model_dump() for c in base if c.name in missing]
            if selected:
                return selected
        return [{"name": n, "keywords": k.split("|")} for n, k in FOLLOWUP_CONCEPTS.get(ftype, FOLLOWUP_CONCEPTS["challenge"])]

    async def _advance(self, state: InterviewState, ctx: EngineContext, out: EngineOutput) -> None:
        r = self._round(state, ctx)
        more = (
            r.kind in ("technical", "behavioral", "introduction", "system_design")
            and state.question_index < r.question_count
            and self._round_left(state, ctx) > 60
            and self._global_left(state, ctx.now) > 90
        )
        if more and await self._ask_next_primary(state, ctx, out):
            return
        await self._complete_round(state, ctx, out)

    async def _complete_round(self, state: InterviewState, ctx: EngineContext, out: EngineOutput) -> None:
        r = self._round(state, ctx)
        state.rounds_completed += 1
        out.round_completed.append(r.id)
        out.events.append(("ROUND_COMPLETED", {"round_id": r.id, "index": state.round_index}))
        await self._enter_round(state, ctx, state.round_index + 1, out)

    async def handle_code_submission(self, state: InterviewState, ctx: EngineContext, submission: CodeSubmissionSummary, statement: str) -> EngineOutput:
        out = EngineOutput()
        if state.phase != Phase.CODING or state.code_state is None or state.current_question is None:
            raise EngineError("No coding question is active")
        state.code_state.submitted = True
        state.code_state.code = submission.code
        coding_q = state.current_question
        if self.defer_scoring:
            score = self.evaluator.quick_score_code(submission)
            out.scored.append(
                ScoredAnswer(
                    question=coding_q,
                    answer=submission.code,
                    score=score,
                    provider="rule-based",
                    refine={"kind": "code", "submission": submission, "problem_statement": statement},
                )
            )
        else:
            score, res = await self.evaluator.score_code(submission, statement)
            out.scored.append(ScoredAnswer(question=coding_q, answer=submission.code, score=score, provider=res.provider, fallback_used=res.fallback_used))
        state.score_history.append(ScoreEntry(qid=coding_q.qid, topic=coding_q.topic, kind="coding", score=score.score))
        state.execution_results.append(
            {"problem_id": submission.problem_id, "passed": submission.passed, "total": submission.total, "status": submission.status}
        )
        review = await self.ai.run(
            AIRequest(
                task="code_review_question",
                schema=CodeReviewQuestion,
                system="You are a technical interviewer reviewing the candidate's submitted code. Ask ONE specific question about their actual "
                "implementation (failing tests, complexity, edge cases or optimisation). Quote their code only verbatim. Do not reveal the fix.",
                prompt=f"Problem: {statement}\nResults: {submission.passed}/{submission.total} ({submission.status}) error={submission.error}\n"
                f"Failures: {[f.model_dump() for f in submission.failures[:2]]}\n<code>\n{submission.code}\n</code>",
                context={"submission": submission.model_dump()},
                effort="low",
                max_tokens=800,
            )
        )
        rq = review.output
        r = self._round(state, ctx)
        aq = AskedQuestion(
            qid=f"{coding_q.qid}#review",
            round_id=r.id,
            topic=coding_q.topic,
            text=rq.question,
            difficulty=coding_q.difficulty,
            kind="code_review",
            parent_qid=None,
            expected_concepts=[{"name": c, "keywords": [c]} for c in rq.expected_concepts],
            asked_at=ctx.now,
        )
        self._move(state, Phase.CODE_REVIEW)
        state.current_question = aq
        state.followups_for_current = 0
        state.next_action = NextAction.WAIT_FOR_ANSWER
        out.asked.append(aq)
        out.say(f"Thanks for submitting. {rq.question}", "question")
        out.events.append(("CODE_REVIEW_STARTED", {"question": aq.model_dump(), "passed": submission.passed, "total": submission.total}))
        return out

    async def end(self, state: InterviewState, ctx: EngineContext, reason: str) -> EngineOutput:
        out = EngineOutput()
        if state.phase in (Phase.FINAL_EVALUATION, Phase.COMPLETED):
            return out
        await self._finish(state, ctx, out, reason)
        return out

    async def check_time(self, state: InterviewState, ctx: EngineContext) -> EngineOutput:
        out = EngineOutput()
        if state.phase not in (Phase.INTERVIEW_SETUP, Phase.FINAL_EVALUATION, Phase.COMPLETED) and self._global_left(state, ctx.now) <= 0:
            await self._finish(state, ctx, out, "time")
        return out

    async def _finish(self, state: InterviewState, ctx: EngineContext, out: EngineOutput, reason: str) -> None:
        self._move(state, Phase.FINAL_EVALUATION)
        state.ended_at = ctx.now
        state.end_reason = reason
        state.current_question = None
        state.next_action = NextAction.GENERATE_REPORT
        msg = {
            "time": "We've reached the end of our time.",
            "candidate": "Understood, we'll stop here.",
            "completed": "That covers everything I wanted to ask.",
        }.get(reason, "We'll wrap up here.")
        out.say(f"{msg} Thank you for your time today. I'm preparing your evaluation now — it will be ready in a moment.", "closing")
        out.events.append(("INTERVIEW_ENDING", {"reason": reason}))
        out.finished = True

    @staticmethod
    def mark_completed(state: InterviewState) -> None:
        assert_transition(state.phase, Phase.COMPLETED)
        state.phase = Phase.COMPLETED
        state.next_action = NextAction.NONE
