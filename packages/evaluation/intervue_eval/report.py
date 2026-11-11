"""Aggregate per-answer scores into the final report. Aggregation is deterministic; only the
narrative prose may come from an LLM, and its factual fields are pinned to computed values."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from pydantic import BaseModel

from intervue_ai import AIClient, AIRequest, register_handler
from intervue_eval.schemas import (
    CATEGORIES,
    AnswerScore,
    CategoryScore,
    Evidence,
    PracticeStep,
    QuestionAnalysis,
    Report,
    ReportNarrative,
    TopicScore,
)

DISCLAIMER = "This assessment is AI-assisted and intended for practice and screening support. It should be reviewed by a person before any hiring decision."

READINESS_LABELS = {
    "ready": "Ready for interviews at this level",
    "nearly_ready": "Nearly ready — close a few gaps",
    "developing": "Developing — focused practice needed",
    "not_yet_ready": "Not yet ready — build fundamentals first",
    "insufficient_data": "Not enough answers to assess readiness",
}


class AnswerRecord(BaseModel):
    question: str
    topic: str
    topic_label: str
    round_kind: str
    kind: str  # primary | followup | code | design
    score: AnswerScore
    weight: float = 1.0


class TimeStats(BaseModel):
    planned_minutes: int
    actual_minutes: float
    rounds_planned: int
    rounds_completed: int
    ended_early: bool = False


def _avg(values: list[float]) -> int | None:
    return round(sum(values) / len(values)) if values else None


def _readiness(overall: int, answered: int) -> str:
    if answered < 3:
        return "insufficient_data"
    if overall >= 80:
        return "ready"
    if overall >= 65:
        return "nearly_ready"
    if overall >= 45:
        return "developing"
    return "not_yet_ready"


@register_handler("report_narrative")
def rule_narrative(ctx: dict[str, Any]) -> ReportNarrative:
    strong = ctx.get("strongest") or "—"
    weak = ctx.get("weakest") or "—"
    readiness = ctx.get("readiness", "developing")
    recs = [f"Practise {t}" for t in ctx.get("recommended_topics", [])[:4]]
    headline = {
        "ready": "Interview-ready performance",
        "nearly_ready": "Solid performance with a few gaps",
        "developing": "Promising foundation; focused practice needed",
        "not_yet_ready": "Build fundamentals before the next attempt",
        "insufficient_data": "Interview too short for a full assessment",
    }.get(readiness, "Interview summary")
    return ReportNarrative(
        headline=headline,
        strongest_area=f"Your strongest area is {strong}." if ctx.get("strongest") else "Not enough data to identify a strongest area.",
        main_weakness=f"Your main weakness is {weak}." if ctx.get("weakest") else "No clear weakness identified from the answers given.",
        summary=ctx.get("transcript_summary", ""),
        recommendations=recs or ["Complete a full-length interview to get detailed recommendations."],
    )


NARRATIVE_SYSTEM = (
    "You write concise, encouraging but honest interview feedback. Use only the facts provided. "
    "Do not invent topics, scores, or experiences. Address the candidate as 'you'."
)


async def build_report(
    records: list[AnswerRecord],
    time_stats: TimeStats,
    topic_weights: dict[str, float],
    practice_hints: dict[str, list[str]],
    coding_summary: list[dict[str, Any]],
    ai: AIClient | None = None,
) -> tuple[Report, Any]:
    cat_values: dict[str, list[float]] = defaultdict(list)
    cat_evidence: dict[str, list[Evidence]] = defaultdict(list)
    topic_vals: dict[str, list[float]] = defaultdict(list)
    topic_labels: dict[str, str] = {}
    missing_counter: Counter[str] = Counter()
    concept_topic: dict[str, str] = {}

    for r in records:
        topic_vals[r.topic].append(r.score.score)
        topic_labels[r.topic] = r.topic_label
        for c in r.score.categories:
            if r.round_kind in ("behavioral", "introduction") and c.category == "technical_correctness":
                continue
            cat_values[c.category].append(c.score)
        for ev in r.score.evidence:
            target = "code_quality" if ev.source == "code" else "architecture" if ev.source == "design" else "technical_correctness"
            if r.round_kind in ("behavioral", "introduction"):
                target = "communication"
            if len(cat_evidence[target]) < 6:
                cat_evidence[target].append(ev)
        if r.score.score < 75 and r.topic != "introduction" and r.kind not in ("followup",):
            for m in r.score.missing_concepts:
                missing_counter[m] += 1
                concept_topic.setdefault(m, r.topic_label)

    # time management is measured, not judged
    if time_stats.rounds_planned:
        completion = time_stats.rounds_completed / time_stats.rounds_planned
        overrun = max(0.0, time_stats.actual_minutes - time_stats.planned_minutes) / max(1, time_stats.planned_minutes)
        tm = max(0, min(100, round(100 * completion - 60 * overrun)))
        cat_values["time_management"].append(tm)
        cat_evidence["time_management"].append(
            Evidence(
                source="execution",
                kind="measurement",
                observation=f"Completed {time_stats.rounds_completed} of {time_stats.rounds_planned} planned rounds in "
                f"{time_stats.actual_minutes:.0f} of {time_stats.planned_minutes} minutes.",
                polarity="positive" if completion >= 0.8 else "negative",
            )
        )

    category_scores = [CategoryScore(category=k, score=v) for k in CATEGORIES if (v := _avg(cat_values.get(k, []))) is not None]

    topic_scores = sorted(
        [TopicScore(topic=t, label=topic_labels[t], score=round(sum(v) / len(v)), answered=len(v)) for t, v in topic_vals.items() if t != "introduction"],
        key=lambda ts: -ts.score,
    )

    # overall: weighted by plan topic weights and answer kind
    num = den = 0.0
    for r in records:
        w = topic_weights.get(r.topic, 0.05) * r.weight
        num += r.score.score * w
        den += w
    overall = round(num / den) if den else 0

    def section(name: str, vals: list[float]) -> CategoryScore | None:
        a = _avg(vals)
        return CategoryScore(category=name, score=a) if a is not None else None

    tech_vals = [r.score.score for r in records if r.round_kind == "technical"]
    coding_vals = [r.score.score for r in records if r.round_kind in ("coding", "sql")]
    design_vals = [r.score.score for r in records if r.round_kind == "system_design"]
    sections = [
        s
        for s in (
            section("technical", tech_vals),
            section("communication", cat_values.get("communication", [])),
            section("problem_solving", cat_values.get("problem_solving", [])),
            section("coding", coding_vals),
            section("system_design", design_vals),
        )
        if s is not None
    ]

    strong = [t.label for t in topic_scores if t.score >= 75]
    weak = [t.label for t in sorted(topic_scores, key=lambda t: t.score) if t.score < 60]
    recommended = [c for c, _ in missing_counter.most_common(8)][:6]

    analyses = [
        QuestionAnalysis(
            question=r.question,
            topic=r.topic_label,
            kind=r.kind,
            score=r.score.score,
            summary=r.score.summary,
            covered=r.score.covered_concepts,
            missing=r.score.missing_concepts,
        )
        for r in records
    ]
    missed = [a for a in analyses if a.score < 45]

    plan: list[PracticeStep] = []
    weak_topics = [t for t in sorted(topic_scores, key=lambda t: t.score) if t.score < 70][:4]
    for i, t in enumerate(weak_topics):
        concepts = [c for c in recommended if concept_topic.get(c) == t.label][:3]
        activities = []
        if concepts:
            activities.append("Review: " + ", ".join(concepts))
        activities.extend(practice_hints.get(t.topic, [])[:2])
        activities.append(f"Answer three {t.label} questions aloud in under 3 minutes each, then self-review.")
        plan.append(PracticeStep(day=f"Days {i * 2 + 1}-{i * 2 + 2}", focus=t.label, activities=activities))
    if plan:
        plan.append(
            PracticeStep(day=f"Day {len(plan) * 2 + 1}", focus="Mock interview", activities=["Take another full mock interview and compare your scores."])
        )

    answered = len([r for r in records if r.kind != "code"])
    readiness = _readiness(overall, answered)
    topics_covered = ", ".join(t.label for t in topic_scores[:6]) or "no technical topics"
    transcript_summary = (
        f"You answered {answered} question(s) across {topics_covered}"
        + (f" and submitted {len(coding_summary)} coding solution(s)" if coding_summary else "")
        + f" over about {time_stats.actual_minutes:.0f} minutes."
    )

    strongest = topic_scores[0].label if topic_scores and topic_scores[0].score >= 50 else None
    weakest = topic_scores[-1].label if topic_scores and topic_scores[-1].score < 75 and len(topic_scores) > 1 else None
    if topic_scores and len(topic_scores) == 1 and topic_scores[0].score < 60:
        weakest, strongest = topic_scores[0].label, None

    ctx = {
        "strongest": strongest,
        "weakest": weakest,
        "readiness": readiness,
        "recommended_topics": recommended,
        "transcript_summary": transcript_summary,
    }
    ai_result = None
    if ai is not None:
        prompt = "Facts:\n" + json.dumps(
            {
                **ctx,
                "overall_score": overall,
                "topic_scores": [t.model_dump() for t in topic_scores],
                "weak_areas": weak,
                "strong_areas": strong,
            }
        )
        ai_result = await ai.run(AIRequest(task="report_narrative", schema=ReportNarrative, system=NARRATIVE_SYSTEM, prompt=prompt, context=ctx, effort="low"))
        narrative = ai_result.output
        # pin factual sentences to computed values
        fixed = rule_narrative(ctx)
        narrative = narrative.model_copy(update={"strongest_area": fixed.strongest_area, "main_weakness": fixed.main_weakness})
    else:
        narrative = rule_narrative(ctx)

    report = Report(
        overall_score=overall,
        section_scores=sections,
        category_scores=category_scores,
        category_evidence={k: v for k, v in cat_evidence.items()},
        role_readiness=readiness,  # type: ignore[arg-type]
        readiness_label=READINESS_LABELS[readiness],
        topic_scores=topic_scores,
        strong_areas=strong,
        weak_areas=weak,
        questions_missed=missed,
        recommended_topics=recommended,
        practice_plan=plan,
        question_analysis=analyses,
        coding_summary=coding_summary,
        transcript_summary=transcript_summary,
        narrative=narrative,
        answered_count=answered,
        disclaimer=DISCLAIMER,
    )
    return report, ai_result
