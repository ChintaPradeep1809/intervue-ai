"""FollowUpAgent and code-review question generation.

The agent picks a follow-up type from the answer quality, prefers curated follow-ups whose trigger
matches what the candidate actually said, and only references phrases present in the answer.
Deterministic guardrails (max follow-ups, time budget, no repeats) always win over the model.
"""

from __future__ import annotations

import json
import re
from typing import Any

from intervue_ai import AIClient, AIRequest, register_handler
from intervue_engine.schemas import LEVEL_NAME, CodeReviewQuestion, FollowUpDecision, PersonalizedQuestion
from intervue_eval.text import find_sentence, keyword_in, normalize

FOLLOWUP_SYSTEM = """You are a professional technical interviewer deciding whether to ask a follow-up question.
Rules:
- Ask at most one short question (max 2 sentences). Be neutral; never reveal or hint at the correct answer; no praise or coaching.
- Base the follow-up only on what the candidate actually said. If you quote them, quote exactly.
- Weak answer -> clarification. Good answer -> challenge or edge_case. Excellent answer -> optimization or architecture at higher difficulty.
- If the candidate said they don't know, do not follow up (should_follow_up=false).
- Prefer one of the curated follow-ups when it fits the answer."""

BANDS = {
    "weak": ["clarification"],
    "good": ["challenge", "edge_case"],
    "excellent": ["optimization", "architecture", "edge_case", "challenge"],
}


def _band(score: int) -> str:
    return "weak" if score < 50 else "good" if score < 80 else "excellent"


def _trigger_ok(trigger: str, covered: list[str], missing: list[str]) -> bool:
    if trigger == "any":
        return True
    kind, _, concept = trigger.partition(":")
    return (kind == "mentioned" and concept in covered) or (kind == "missing" and concept in missing)


def _said_phrase(answer: str, concepts: list[dict[str, Any]], covered: list[str]) -> str | None:
    norm = normalize(answer)
    for c in concepts:
        if c["name"] in covered:
            for kw in c.get("keywords", []):
                if keyword_in(kw, norm) and len(kw) > 3 and kw.lower() in answer.lower():
                    idx = answer.lower().find(kw.lower())
                    return answer[idx : idx + len(kw)]
    return None


@register_handler("generate_followup")
def rule_followup(ctx: dict[str, Any]) -> FollowUpDecision:
    score = int(ctx["score"])
    covered: list[str] = ctx.get("covered", [])
    missing: list[str] = ctx.get("missing", [])
    used = set(ctx.get("used_followups", []))
    round_kind = ctx.get("round_kind", "technical")
    nf = int(ctx.get("followups_for_current", 0))
    level = int(ctx.get("difficulty", 2))
    band = _band(score)
    no = FollowUpDecision(should_follow_up=False, type="clarification", question="", reason="", expected_concepts=[], difficulty=LEVEL_NAME[level])  # type: ignore[arg-type]

    if not ctx.get("time_ok", True) or nf >= int(ctx.get("max_followups", 2)) or ctx.get("dont_know"):
        return no.model_copy(update={"reason": "Guardrail: no follow-up (time, limit, or no attempt)."})
    if nf >= 1 and band == "weak":
        return no.model_copy(update={"reason": "Already clarified once; moving on."})
    if round_kind == "introduction" and (nf >= 1 or not ctx.get("bank_followups")):
        return no

    preferred = ["behavioral"] if round_kind == "behavioral" else BANDS[band]
    options = [f for f in ctx.get("bank_followups", []) if f["text"] not in used and _trigger_ok(f["trigger"], covered, missing)]

    def rank(f: dict[str, Any]) -> tuple[int, int]:
        type_rank = preferred.index(f["type"]) if f["type"] in preferred else len(preferred) + 1
        specific = 0 if f["trigger"] != "any" else 1
        return (type_rank, specific)

    options.sort(key=rank)
    new_level = min(3, level + 1) if band == "excellent" else max(1, level - 1) if band == "weak" else level
    if options and (options[0]["type"] in preferred or band != "weak"):
        f = options[0]
        concept = f["trigger"].partition(":")[2]
        return FollowUpDecision(
            should_follow_up=True,
            type=f["type"],
            question=f["text"],
            reason=f"{band} answer ({score}); curated follow-up triggered by {f['trigger']}.",
            expected_concepts=[concept] if concept else [],
            difficulty=LEVEL_NAME[new_level],  # type: ignore[arg-type]
        )
    phrase = _said_phrase(ctx.get("answer", ""), ctx.get("expected_concepts", []), covered)
    if band == "weak":
        q = (
            f"You mentioned {phrase}. Can you be more specific about how that works in practice?"
            if phrase
            else "Could you walk me through a concrete example of how you'd approach this, step by step?"
        )
        ftype = "clarification"
    elif round_kind == "behavioral":
        q, ftype = "What was the measurable outcome, and what would you do differently next time?", "behavioral"
    else:
        q = (
            f"You brought up {phrase}. What trade-offs or failure modes would you watch for with that approach?"
            if phrase
            else "What would break first in your approach if the data volume grew a hundred times?"
        )
        ftype = "challenge"
    if q in used:
        return no.model_copy(update={"reason": "Template follow-up already used."})
    return FollowUpDecision(
        should_follow_up=True,
        type=ftype,  # type: ignore[arg-type]
        question=q,
        reason=f"{band} answer ({score}).",
        expected_concepts=[],
        difficulty=LEVEL_NAME[new_level],  # type: ignore[arg-type]
    )


class FollowUpAgent:
    def __init__(self, ai: AIClient, max_followups: int = 2) -> None:
        self.ai = ai
        self.max_followups = max_followups

    async def decide(
        self,
        *,
        question: str,
        answer: str,
        score: int,
        covered: list[str],
        missing: list[str],
        expected_concepts: list[dict[str, Any]],
        bank_followups: list[dict[str, Any]],
        used_followups: list[str],
        followups_for_current: int,
        round_kind: str,
        topic_label: str,
        difficulty: int,
        time_ok: bool,
        dont_know: bool,
        recent_context: str,
        objective: str,
        tools: list[Any] | None = None,
    ) -> tuple[FollowUpDecision, Any]:
        ctx = {
            "answer": answer,
            "score": score,
            "covered": covered,
            "missing": missing,
            "expected_concepts": expected_concepts,
            "bank_followups": bank_followups,
            "used_followups": used_followups,
            "followups_for_current": followups_for_current,
            "max_followups": self.max_followups,
            "round_kind": round_kind,
            "difficulty": difficulty,
            "time_ok": time_ok,
            "dont_know": dont_know,
        }
        guard = rule_followup(ctx)
        if not guard.should_follow_up and guard.reason.startswith(("Guardrail", "Already")):
            return guard, None  # deterministic stop: no AI call needed
        prompt = (
            f"Interview objective: {objective}\nRound: {round_kind} / topic: {topic_label}\n"
            f"Follow-ups already asked for this question: {followups_for_current} (max {self.max_followups})\n"
            f"Recent context: {recent_context or 'n/a'}\n"
            f"Question: {question}\n<answer>\n{answer}\n</answer>\n"
            f"Evaluator score: {score}/100; covered: {covered}; missing: {missing}\n"
            f"Curated follow-ups: {json.dumps([{'type': f['type'], 'text': f['text']} for f in bank_followups if f['text'] not in used_followups])}\n"
            "Decide the follow-up."
        )
        result = await self.ai.run(
            AIRequest(
                task="generate_followup",
                schema=FollowUpDecision,
                system=FOLLOWUP_SYSTEM,
                prompt=prompt,
                context=ctx,
                tools=tools or [],
                effort="low",
                max_tokens=1500,
            )
        )
        d = result.output
        if d.should_follow_up:
            q = d.question.strip()
            if not q or q in used_followups or len(q) > 400 or q.lower() == question.lower():
                d = guard
        return d, result


@register_handler("code_review_question")
def rule_code_review(ctx: dict[str, Any]) -> CodeReviewQuestion:
    sub = ctx["submission"]
    is_sql = sub["language"] == "sql"
    complexity = ["time complexity", "space complexity", "o(n)", "o(n log n)", "linear", "constant"]
    if sub["status"] in ("error", "timeout"):
        err = (sub.get("error") or "an error").strip().splitlines()[-1][:160]
        return CodeReviewQuestion(
            question=f'Your last run ended with: "{err}". What\'s causing that, and how would you fix it?',
            focus="debugging",
            expected_concepts=["root cause", "fix"],
        )
    if sub["passed"] < sub["total"]:
        vis = [f for f in sub.get("failures", []) if f.get("expected") not in (None, "", "hidden")]
        if vis:
            f = vis[0]
            q = f"For the '{f['name']}' case your solution returned {f['actual']} but {f['expected']} was expected. Walk me through why."
        elif is_sql:
            q = "Your query's result doesn't match the expected output. What do you think is causing the difference?"
        else:
            q = f"Your solution passes the examples but fails {sub['total'] - sub['passed']} hidden test(s). Which edge cases might you be missing?"
        return CodeReviewQuestion(question=q, focus="failing_tests", expected_concepts=["edge case", "empty input", "ties", "duplicates", "boundary"])
    code = sub["code"]
    if is_sql:
        if re.search(r"select\s+\*", code, re.I):
            q = "Your query is correct. You used SELECT * in it — how would you optimize this query for a billion-row orders table?"
        else:
            q = "Your query returns the correct result. How would you optimize it if the orders table had a billion rows?"
        return CodeReviewQuestion(
            question=q, focus="optimization", expected_concepts=["index", "partition", "filter early", "explain", "pre-aggregate", "columns"]
        )
    if re.search(r"^(\s*)for\b.*\n(?:\1\s+.*\n)*?\1\s+for\b", code, re.M):
        return CodeReviewQuestion(
            question="All tests pass. I notice nested loops in your solution — what's its time complexity, and can you do better?",
            focus="complexity",
            expected_concepts=complexity + ["hash", "dictionary", "set"],
        )
    return CodeReviewQuestion(
        question="All tests pass. What are the time and space complexity of your solution, and how would it behave on ten million records?",
        focus="complexity",
        expected_concepts=complexity,
    )


@register_handler("personalize_question")
def rule_personalize(ctx: dict[str, Any]) -> PersonalizedQuestion:
    skill = ctx.get("matching_skill")
    text = ctx["question"]
    if skill:
        return PersonalizedQuestion(text=f"Your resume mentions {skill}. {text}", referenced_skill=skill)
    return PersonalizedQuestion(text=text, referenced_skill=None)


__all__ = ["FollowUpAgent", "find_sentence", "rule_code_review", "rule_followup", "rule_personalize"]
