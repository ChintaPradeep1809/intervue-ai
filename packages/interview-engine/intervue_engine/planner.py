"""Interview plan generation: deterministic layout + topic prioritisation from the analysis."""

from __future__ import annotations

from typing import Any

from intervue_engine.roles import RoleConfig, get_role
from intervue_engine.schemas import InterviewPlan, PlanRound, ResumeAnalysis, SkillWeight
from intervue_engine.taxonomy import topic_label

INTERVIEW_TYPES = ["technical", "coding", "system_design", "behavioral", "full"]


def _boosted_topics(role: RoleConfig, analysis: ResumeAnalysis | None) -> list[tuple[str, float]]:
    weights = dict(role.topic_weights)
    if analysis:
        gaps = {g.lower() for g in analysis.skill_gaps}
        for t in analysis.priority_topics:
            if t in weights:
                weights[t] *= 1.5
            elif t not in ("behavioral", "system_design", "introduction"):
                weights[t] = 0.05  # JD-required topic outside the role profile
        for t in list(weights):
            if topic_label(t).lower() in gaps:
                weights[t] *= 1.2
    total = sum(weights.values()) or 1.0
    return sorted(((t, w / total) for t, w in weights.items()), key=lambda x: -x[1])


def _split_topics(ranked: list[tuple[str, float]], n_rounds: int, max_topics: int) -> list[list[str]]:
    chosen = [t for t, _ in ranked[:max_topics]]
    groups: list[list[str]] = [[] for _ in range(max(1, n_rounds))]
    for i, t in enumerate(chosen):
        groups[i % len(groups)].append(t)
    return [g for g in groups if g]


def _title(topics: list[str]) -> str:
    labels = [topic_label(t) for t in topics[:3]]
    return " & ".join(labels) if len(labels) <= 2 else f"{labels[0]}, {labels[1]} & {labels[2]}"


def build_plan(
    role_key: str,
    interview_type: str,
    duration_minutes: int,
    difficulty: str,
    analysis: ResumeAnalysis | None = None,
    template_rounds: list[dict[str, Any]] | None = None,
) -> InterviewPlan:
    role = get_role(role_key)
    itype = interview_type if interview_type in INTERVIEW_TYPES else "full"
    duration = max(10, min(90, int(duration_minutes)))
    ranked = _boosted_topics(role, analysis)
    rounds: list[PlanRound] = []
    rationale: list[str] = []

    def add(kind: str, minutes: int, topics: list[str] | None = None, title: str | None = None, language: str | None = None) -> None:
        topics = topics or []
        if kind == "technical":
            qc = max(2, minutes // 4)
        elif kind == "behavioral":
            qc = max(1, minutes // 4)
        else:
            qc = 1
        default_titles = {
            "introduction": "Introduction",
            "coding": "Live coding",
            "sql": "SQL challenge",
            "system_design": "System design",
            "behavioral": "Behavioral",
        }
        rounds.append(
            PlanRound(
                id=f"r{len(rounds) + 1}",
                kind=kind,  # type: ignore[arg-type]
                title=title or (default_titles.get(kind) or _title(topics)),
                topics=topics,
                minutes=minutes,
                question_count=qc,
                language=language,
            )
        )

    if template_rounds:
        for tr in template_rounds:
            add(tr["kind"], int(tr.get("minutes", 10)), list(tr.get("topics", [])), tr.get("title"), tr.get("language"))
            if tr.get("question_count"):
                rounds[-1].question_count = int(tr["question_count"])
        rationale.append("Rounds follow the organisation's interview template.")
    else:
        coding_kind = "sql" if role.coding_language == "sql" else "coding"
        coding_lang = "sql" if coding_kind == "sql" else role.coding_language
        coding_topic = "sql" if coding_kind == "sql" else ("python" if "python" in role.topic_weights else "algorithms")
        design_ok = bool(role.design_tags)
        if itype == "behavioral":
            add("introduction", 3, ["introduction"])
            add("behavioral", duration - 3, ["behavioral"])
        elif itype == "system_design":
            add("introduction", 3, ["introduction"])
            add("system_design", int(duration * 0.65), ["system_design"])
            for g in _split_topics(ranked, 1, 3):
                add("technical", duration - 3 - int(duration * 0.65), g)
        elif itype == "coding":
            add("introduction", 2, ["introduction"])
            main = int(duration * 0.55)
            add(coding_kind, main, [coding_topic], language=coding_lang)
            if role.has_sql_round and coding_kind != "sql":
                add("sql", duration - 2 - main, ["sql"], language="sql")
            else:
                add("technical", duration - 2 - main, [t for t, _ in ranked[:2]])
        elif itype == "technical":
            add("introduction", 3, ["introduction"])
            n = 2 if duration >= 30 else 1
            groups = _split_topics(ranked, n, 6 if n == 2 else 3)
            per = (duration - 3) // len(groups)
            for g in groups:
                add("technical", per, g)
        else:  # full
            if duration <= 35:
                add("introduction", 3, ["introduction"])
                for g in _split_topics(ranked, 1, 4):
                    add("technical", duration - 18, g)
                add(coding_kind, 10, [coding_topic], language=coding_lang)
                add("behavioral", 5, ["behavioral"])
            elif duration <= 50:
                add("introduction", 4, ["introduction"])
                for g in _split_topics(ranked, 1, 5):
                    add("technical", duration - 31 if design_ok else duration - 21, g)
                add(coding_kind, 12, [coding_topic], language=coding_lang)
                if design_ok:
                    add("system_design", 10, ["system_design"])
                add("behavioral", 5, ["behavioral"])
            else:
                add("introduction", 4, ["introduction"])
                sql_extra = role.has_sql_round and coding_kind != "sql"
                fixed = 4 + 12 + (10 if sql_extra else 0) + (12 if design_ok else 0) + 6
                groups = _split_topics(ranked, 2, 6)
                per = (duration - fixed) // len(groups)
                for g in groups:
                    add("technical", per, g)
                if sql_extra:
                    add("sql", 10, ["sql"], language="sql")
                add(coding_kind, 12, [coding_topic], language=coding_lang)
                if design_ok:
                    add("system_design", 12, ["system_design"])
                add("behavioral", 6, ["behavioral"])
        if analysis and analysis.priority_topics:
            rationale.append("Topics prioritised from the job requirements: " + ", ".join(topic_label(t) for t in analysis.priority_topics[:5]) + ".")
        if analysis and analysis.skill_gaps:
            rationale.append("Includes requirements not evidenced in the resume: " + ", ".join(analysis.skill_gaps[:4]) + ".")
        if analysis and analysis.skills:
            rationale.append("Resume skills that may be referenced: " + ", ".join(s.name for s in analysis.skills[:6]) + ".")

    # skill weights from minutes allocation
    minutes_by_topic: dict[str, float] = {}
    tw = dict(ranked)
    for r in rounds:
        if r.kind == "technical" and r.topics:
            tot = sum(tw.get(t, 0.05) for t in r.topics) or 1
            for t in r.topics:
                minutes_by_topic[t] = minutes_by_topic.get(t, 0) + r.minutes * tw.get(t, 0.05) / tot
        else:
            key = r.topics[0] if r.topics else r.kind
            minutes_by_topic[key] = minutes_by_topic.get(key, 0) + r.minutes
    total_min = sum(minutes_by_topic.values()) or 1
    weights = [
        SkillWeight(topic=t, label="Communication" if t == "introduction" else topic_label(t), weight=round(m / total_min, 3))
        for t, m in sorted(minutes_by_topic.items(), key=lambda x: -x[1])
    ]
    exp = analysis.experience_level if analysis else role.default_experience
    return InterviewPlan(
        role_key=role.key,
        role_title=role.title,
        experience_level=exp,  # type: ignore[arg-type]
        difficulty=difficulty if difficulty in ("easy", "medium", "hard") else "medium",  # type: ignore[arg-type]
        interview_type=itype,
        duration_minutes=sum(r.minutes for r in rounds),
        rounds=rounds,
        skill_weights=weights,
        total_questions=sum(r.question_count for r in rounds),
        rationale=rationale,
        personalized_from_resume=bool(analysis and analysis.skills),
    )
