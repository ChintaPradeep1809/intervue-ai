"""Answer, code and design scoring.

`EvaluationProvider` runs the `score_answer` / `score_code` tasks through the AI client. The
deterministic handlers below are registered with the mock provider; LLM outputs go through the
same post-processing, which drops any evidence that cannot be found verbatim in the source.
"""

from __future__ import annotations

import json
import re
from typing import Any

from intervue_ai import AIClient, AIRequest, register_handler
from intervue_eval.schemas import (
    AnswerScore,
    CategoryScore,
    CodeSubmissionSummary,
    Evidence,
    ExpectedConcept,
)
from intervue_eval.text import (
    DONT_KNOW,
    FILLER,
    NUMBER,
    REASONING,
    TRADEOFF,
    find_sentence,
    keyword_in,
    normalize,
    quote_in_source,
    sentences,
    word_count,
)

EVALUATOR_SYSTEM = """You are a rigorous, neutral technical interview evaluator.
Score the candidate's answer from 0-100 against the question and expected concepts.
Rules:
- Base every judgement on the candidate's actual words, code or design. Never assume knowledge the candidate did not demonstrate.
- Evidence quotes MUST be copied verbatim from the provided answer/code/design text. If you cannot quote, use kind="absence" with an empty quote.
- Do not reward length or confidence on its own; reward correctness, depth, reasoning and trade-off awareness.
- Calibration: 90+ exceptional and precise; 75-89 strong with minor gaps; 55-74 adequate but shallow or partially wrong; 35-54 weak; <35 incorrect or missing.
- Categories to score: technical_correctness, depth_of_knowledge, problem_solving, communication, tradeoffs (plus code_quality, debugging for code; architecture for design).
- covered_concepts and missing_concepts must contain only the exact concept names given in the expected concepts list.
- Be concise: at most 4 evidence items, one short sentence per observation and per strength/weakness."""


def _clamp(v: float) -> int:
    return int(max(0, min(100, round(v))))


def _concepts(ctx: dict[str, Any]) -> list[ExpectedConcept]:
    return [ExpectedConcept.model_validate(c) for c in ctx.get("expected_concepts", [])]


def match_concepts(text: str, concepts: list[ExpectedConcept]) -> tuple[list[ExpectedConcept], list[ExpectedConcept], dict[str, str]]:
    norm = normalize(text)
    covered, missing, hit_keyword = [], [], {}
    for c in concepts:
        kw = next((k for k in c.keywords if keyword_in(k, norm)), None)
        if kw:
            covered.append(c)
            hit_keyword[c.name] = kw
        else:
            missing.append(c)
    return covered, missing, hit_keyword


@register_handler("score_answer")
def rule_score_answer(ctx: dict[str, Any]) -> AnswerScore:
    answer: str = ctx.get("answer", "") or ""
    design_text: str = ctx.get("design_text", "") or ""
    round_kind: str = ctx.get("round_kind", "technical")
    concepts = _concepts(ctx)
    combined = f"{answer}\n{design_text}"
    words = word_count(answer)

    if DONT_KNOW.search(answer) and words < 25:
        return AnswerScore(
            score=8,
            categories=[CategoryScore(category=c, score=8) for c in ("technical_correctness", "depth_of_knowledge", "problem_solving")]
            + [CategoryScore(category="communication", score=45)],
            covered_concepts=[],
            missing_concepts=[c.name for c in concepts],
            evidence=[
                Evidence(
                    source="transcript",
                    kind="quote",
                    quote=answer.strip()[:160],
                    observation="Candidate indicated they did not know the answer.",
                    polarity="negative",
                )
            ]
            if answer.strip()
            else [],
            strengths=[],
            weaknesses=[f"Could not answer: {ctx.get('topic_label', ctx.get('topic', 'this topic'))}"],
            summary="The candidate did not attempt an answer.",
            confidence=0.9,
        )

    covered, missing, hits = match_concepts(combined, concepts)
    coverage = len(covered) / len(concepts) if concepts else min(1.0, words / 80)
    reasoning = min(1.0, len(REASONING.findall(answer)) / 3)
    specificity = min(1.0, (len(NUMBER.findall(answer)) + len(hits)) / 5)
    tradeoff = min(1.0, len(TRADEOFF.findall(answer)) / 2)
    length_factor = min(1.0, words / 90)
    filler_ratio = len(FILLER.findall(answer)) / max(1, words)
    sent = sentences(answer)
    avg_sent = words / max(1, len(sent))

    technical = 18 + 72 * coverage + 10 * specificity
    depth = 15 + 45 * coverage + 25 * length_factor + 15 * specificity
    problem = 25 + 35 * coverage + 40 * reasoning
    comm = 55 + 25 * min(1.0, words / 40) + 10 * (1 if 6 <= avg_sent <= 30 else 0) - 120 * filler_ratio
    if words > 350:
        comm -= 10
    trade = 25 + 75 * tradeoff * (0.5 + 0.5 * coverage)

    cats = {
        "technical_correctness": technical,
        "depth_of_knowledge": depth,
        "problem_solving": problem,
        "communication": comm,
        "tradeoffs": trade,
    }
    weights = {"technical_correctness": 0.4, "depth_of_knowledge": 0.2, "problem_solving": 0.15, "communication": 0.15, "tradeoffs": 0.1}
    if round_kind == "behavioral" or round_kind == "introduction":
        weights = {"technical_correctness": 0.0, "depth_of_knowledge": 0.2, "problem_solving": 0.3, "communication": 0.4, "tradeoffs": 0.1}
        cats["technical_correctness"] = technical  # STAR coverage, reported but not weighted
    if round_kind == "system_design":
        arch = 15 + 65 * coverage + 20 * min(1.0, design_text.count("->") / 4)
        cats["architecture"] = arch
        weights = {
            "technical_correctness": 0.25,
            "architecture": 0.3,
            "depth_of_knowledge": 0.1,
            "problem_solving": 0.1,
            "communication": 0.1,
            "tradeoffs": 0.15,
        }
    overall = sum(cats[k] * w for k, w in weights.items())
    if words < 8 and not design_text:
        overall = min(overall, 22)
    elif words < 20 and not design_text:
        overall = min(overall, 45)

    evidence: list[Evidence] = []
    for c in covered:
        kw = hits[c.name]
        quote = find_sentence(answer, kw)
        if quote:
            evidence.append(Evidence(source="transcript", quote=quote, observation=f"Addressed {c.name}.", polarity="positive"))
        elif design_text and keyword_in(kw, normalize(design_text)):
            q = find_sentence(design_text, kw) or kw
            evidence.append(Evidence(source="design", quote=q, observation=f"Design includes {c.name}.", polarity="positive"))
    for c in missing[:3]:
        evidence.append(Evidence(source="transcript", kind="absence", observation=f"Did not address {c.name}.", polarity="negative"))

    topic_label = ctx.get("topic_label", ctx.get("topic", "topic"))
    strengths = [f"{topic_label}: explained {c.name}" for c in covered[:3]]
    weaknesses = [f"{topic_label}: {c.name}" for c in missing[:3]]
    if overall >= 75:
        summary = f"Strong answer covering {len(covered)} of {len(concepts)} key concepts with clear reasoning."
    elif overall >= 55:
        summary = f"Reasonable answer covering {len(covered)} of {len(concepts)} key concepts; some depth missing."
    else:
        summary = f"Limited answer covering {len(covered)} of {len(concepts) or 'the'} key concepts."
    return AnswerScore(
        score=_clamp(overall),
        categories=[CategoryScore(category=k, score=_clamp(v)) for k, v in cats.items()],
        covered_concepts=[c.name for c in covered],
        missing_concepts=[c.name for c in missing],
        evidence=evidence,
        strengths=strengths,
        weaknesses=weaknesses,
        summary=summary,
        confidence=0.55 if not concepts else 0.7,
    )


_SQL_PERF = [
    (re.compile(r"select\s+\*", re.I), "Uses SELECT *, which reads unnecessary columns."),
    (re.compile(r"where\s+\w+\s*\(\s*\w+", re.I), "Applies a function to a column in WHERE, which can prevent index/partition pruning."),
    (re.compile(r"select\s+distinct", re.I), "Uses DISTINCT, which may hide a join fan-out."),
]


@register_handler("score_code")
def rule_score_code(ctx: dict[str, Any]) -> AnswerScore:
    sub = CodeSubmissionSummary.model_validate(ctx["submission"])
    code = sub.code
    lines = [ln for ln in code.splitlines() if ln.strip()]
    correctness = 100 * sub.passed / sub.total if sub.total else 0
    if sub.status in ("error", "timeout"):
        correctness = min(correctness, 15)
    evidence: list[Evidence] = [
        Evidence(
            source="execution",
            kind="measurement",
            observation=f"Passed {sub.passed} of {sub.total} test cases" + (f" ({sub.status}: {sub.error[:120]})" if sub.error else "") + ".",
            polarity="positive" if sub.passed == sub.total and sub.total else "negative",
        )
    ]
    quality = 60.0
    strengths: list[str] = []
    weaknesses: list[str] = []
    norm_code = code.lower()
    if sub.language == "sql":
        used = [f for f in sub.expected_features if keyword_in(f, normalize(code))]
        quality = 55 + 30 * (len(used) / max(1, len(sub.expected_features)))
        for f in used:
            q = find_sentence(code, f.split()[0]) or f
            evidence.append(Evidence(source="code", quote=q, observation=f"Uses {f}.", polarity="positive"))
        for pattern, note in _SQL_PERF:
            m = pattern.search(code)
            if m:
                quality -= 8
                evidence.append(Evidence(source="code", quote=m.group(0), observation=note, polarity="negative"))
                weaknesses.append(note)
        if "--" in code:
            quality += 4
    else:
        idents = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", code)
        short = [i for i in idents if len(i) == 1 and i not in ("i", "j", "k", "n", "x", "_")]
        if short and len(short) / max(1, len(idents)) > 0.15:
            quality -= 10
            weaknesses.append("Many single-letter variable names reduce readability.")
        if re.search(r"#|//|\"\"\"", code):
            quality += 6
            strengths.append("Code includes comments or docstrings.")
        if re.search(r"except\s*:", code):
            quality -= 10
            m = re.search(r"except\s*:", code)
            if m:
                evidence.append(Evidence(source="code", quote=m.group(0), observation="Bare except swallows errors.", polarity="negative"))
        loops = len(re.findall(r"^\s*(for|while)\b", code, re.M))
        nested = re.search(r"^(\s*)for\b.*\n(?:\1\s+.*\n)*?\1\s+for\b", code, re.M)
        if nested:
            quality -= 5
            evidence.append(
                Evidence(source="code", quote=nested.group(0).strip().splitlines()[0], observation="Nested loops suggest O(n^2) time.", polarity="negative")
            )
        if any(k in norm_code for k in ("dict(", "{}", "set(", "map(", "new map", "new set", "collections")) and loops <= 1:
            quality += 8
            strengths.append("Uses hash-based data structures for efficient lookup.")
        if len(lines) > 60:
            quality -= 5
    debugging = 70.0
    if sub.run_count > 1 and sub.passed == sub.total:
        debugging = 80
        evidence.append(
            Evidence(
                source="execution", kind="measurement", observation=f"Iterated over {sub.run_count} runs to reach a passing solution.", polarity="positive"
            )
        )
    elif sub.status == "error":
        debugging = 35
    problem = 30 + 0.6 * correctness
    overall = 0.6 * correctness + 0.25 * quality + 0.15 * debugging
    if sub.passed == sub.total and sub.total:
        strengths.append(f"{sub.problem_title}: all tests passing.")
    else:
        weaknesses.append(f"{sub.problem_title}: {sub.total - sub.passed} failing test(s).")
    return AnswerScore(
        score=_clamp(overall),
        categories=[
            CategoryScore(category="technical_correctness", score=_clamp(correctness)),
            CategoryScore(category="code_quality", score=_clamp(quality)),
            CategoryScore(category="debugging", score=_clamp(debugging)),
            CategoryScore(category="problem_solving", score=_clamp(problem)),
        ],
        covered_concepts=[],
        missing_concepts=[],
        evidence=evidence,
        strengths=strengths,
        weaknesses=weaknesses,
        summary=f"Solution passed {sub.passed}/{sub.total} tests.",
        confidence=0.8,
    )


def verify_evidence(score: AnswerScore, sources: dict[str, str]) -> AnswerScore:
    """Drop any quote that does not appear verbatim in its claimed source."""
    kept: list[Evidence] = []
    for ev in score.evidence:
        if ev.kind == "quote":
            src = sources.get(ev.source, "")
            if not ev.quote or not quote_in_source(ev.quote, src):
                continue
        kept.append(ev)
    dropped = len(score.evidence) - len(kept)
    confidence = score.confidence
    if dropped:
        confidence = max(0.2, confidence - 0.1 * dropped)
    return score.model_copy(update={"evidence": kept, "confidence": confidence})


class EvaluationProvider:
    """Scores answers/code via the AI client, then enforces evidence verification."""

    def __init__(self, ai: AIClient) -> None:
        self.ai = ai

    async def score_answer(
        self,
        *,
        question: str,
        answer: str,
        topic: str,
        topic_label: str,
        round_kind: str,
        expected_concepts: list[ExpectedConcept],
        design_text: str = "",
        recent_context: str = "",
    ) -> tuple[AnswerScore, Any]:
        ctx = {
            "question": question,
            "answer": answer,
            "topic": topic,
            "topic_label": topic_label,
            "round_kind": round_kind,
            "expected_concepts": [c.model_dump() for c in expected_concepts],
            "design_text": design_text,
        }
        prompt = (
            f"Round: {round_kind}\nTopic: {topic_label}\nQuestion: {question}\n"
            f"Expected concepts (guidance, not a checklist): {json.dumps([c.name for c in expected_concepts])}\n"
            + (f"Recent interview context: {recent_context}\n" if recent_context else "")
            + (f"Candidate's architecture diagram:\n<design>\n{design_text}\n</design>\n" if design_text else "")
            + f"Candidate's answer (transcribed speech):\n<answer>\n{answer}\n</answer>"
        )
        result = await self.ai.run(AIRequest(task="score_answer", schema=AnswerScore, system=EVALUATOR_SYSTEM, prompt=prompt, context=ctx, effort="low"))
        verified = verify_evidence(result.output, {"transcript": answer, "design": design_text})
        return normalize_concepts(verified, expected_concepts, answer + "\n" + design_text), result

    def quick_score_answer(
        self,
        *,
        answer: str,
        topic: str,
        topic_label: str,
        round_kind: str,
        expected_concepts: list[ExpectedConcept],
        design_text: str = "",
    ) -> AnswerScore:
        """Instant deterministic score used to route follow-ups while the LLM score is refined in the background."""
        ctx = {
            "answer": answer,
            "topic": topic,
            "topic_label": topic_label,
            "round_kind": round_kind,
            "expected_concepts": [c.model_dump() for c in expected_concepts],
            "design_text": design_text,
        }
        return verify_evidence(rule_score_answer(ctx), {"transcript": answer, "design": design_text})

    def quick_score_code(self, submission: CodeSubmissionSummary) -> AnswerScore:
        return verify_evidence(rule_score_code({"submission": submission.model_dump()}), {"code": submission.code, "execution": ""})

    async def score_code(self, submission: CodeSubmissionSummary, problem_statement: str) -> tuple[AnswerScore, Any]:
        prompt = (
            f"Problem: {submission.problem_title}\n{problem_statement}\n\nLanguage: {submission.language}\n"
            f"Test results: passed {submission.passed}/{submission.total}, status={submission.status}, error={submission.error}\n"
            f"Failures: {json.dumps([f.model_dump() for f in submission.failures][:3])}\n"
            f"Candidate code:\n<code>\n{submission.code}\n</code>\n"
            "Score correctness (from the test results), code_quality, debugging and problem_solving. Quote code verbatim."
        )
        result = await self.ai.run(
            AIRequest(
                task="score_code", schema=AnswerScore, system=EVALUATOR_SYSTEM, prompt=prompt, context={"submission": submission.model_dump()}, effort="low"
            )
        )
        verified = verify_evidence(result.output, {"code": submission.code, "execution": ""})
        # Correctness is measured, not judged: pin it to the actual test results.
        measured = _clamp(100 * submission.passed / submission.total) if submission.total else 0
        if submission.status in ("error", "timeout"):
            measured = min(measured, 15)
        cats = [c for c in verified.categories if c.category != "technical_correctness"]
        cats.insert(0, CategoryScore(category="technical_correctness", score=measured))
        return verified.model_copy(update={"categories": cats}), result


def normalize_concepts(score: AnswerScore, expected: list[ExpectedConcept], text: str) -> AnswerScore:
    """Pin covered/missing concepts to the known concept names. Models sometimes paraphrase them, which
    would leak free text into recommendations; fall back to keyword matching when they don't match."""
    names = [c.name for c in expected]
    if not names:
        return score
    lower = {n.lower(): n for n in names}
    covered = [lower[c.lower()] for c in score.covered_concepts if c.lower() in lower]
    if not covered and score.covered_concepts:
        covered = [c.name for c in match_concepts(text, expected)[0]]
    covered = list(dict.fromkeys(covered))
    missing = [n for n in names if n not in covered]
    return score.model_copy(update={"covered_concepts": covered, "missing_concepts": missing})
