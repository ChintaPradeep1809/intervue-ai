"""Resume + job description analysis.

The LLM path produces a `ResumeAnalysis`; every claimed resume skill is then verified against the
resume text and dropped if it cannot be found. The deterministic path uses the skill taxonomy.
"""

from __future__ import annotations

import re
from typing import Any

from intervue_ai import AIClient, AIRequest, register_handler
from intervue_engine.roles import ROLES, get_role
from intervue_engine.schemas import LEVEL_NAME, ResumeAnalysis, SkillEvidence
from intervue_engine.taxonomy import SKILLS, TOPICS, topic_label

ANALYSIS_SYSTEM = """You analyse a candidate's resume against a job description for a technical interview.
Rules:
- Only list a skill under `skills` if it literally appears in the resume; `evidence` must be a short verbatim excerpt of the resume.
- Never infer experience the resume does not state.
- `job_requirements` come only from the job description (or the role description if no JD).
- `skill_gaps` are requirements with no matching resume evidence.
- Topics must be chosen from this list: {topics}.
"""

_YEARS = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years|yrs|year)(?:\s+of)?(?:\s+\w+){0,3}\s+experience", re.I)
_YEARS_ALT = re.compile(r"experience\s*(?:of|:)?\s*(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years|yrs)", re.I)
_NAME_LINE = re.compile(r"^[A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){1,3}$")


def _alias_hit(alias: str, text_l: str) -> int:
    a = alias.lower()
    if re.fullmatch(r"[a-z0-9]+", a):
        m = re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", text_l)
    else:
        idx = text_l.find(a)
        return idx
    return m.start() if m else -1


def _snippet(text: str, idx: int, length: int) -> str:
    start = max(0, idx - 40)
    end = min(len(text), idx + length + 40)
    snip = text[start:end]
    if start > 0 and " " in snip:
        snip = snip[snip.index(" ") + 1 :]
    if end < len(text) and " " in snip:
        snip = snip[: snip.rindex(" ")]
    return " ".join(snip.split())


def extract_skills(text: str) -> list[SkillEvidence]:
    text_l = text.lower()
    found: dict[str, SkillEvidence] = {}
    for sk in SKILLS:
        for alias in sk.aliases:
            idx = _alias_hit(alias, text_l)
            if idx >= 0:
                found[sk.name] = SkillEvidence(name=sk.name, topic=sk.topic, evidence=_snippet(text, idx, len(alias)))
                break
    return list(found.values())


def estimate_years(text: str) -> float | None:
    vals = [float(m.group(1)) for rx in (_YEARS, _YEARS_ALT) for m in rx.finditer(text)]
    vals = [v for v in vals if 0 < v < 45]
    return max(vals) if vals else None


def level_for_years(years: float | None, fallback: str) -> str:
    if years is None:
        return fallback
    if years < 1:
        return "entry"
    if years < 3:
        return "junior"
    if years < 6:
        return "mid"
    if years < 10:
        return "senior"
    return "lead"


def guess_name(text: str) -> str | None:
    for line in text.splitlines()[:5]:
        line = line.strip()
        if _NAME_LINE.match(line) and len(line) < 40:
            return line
    return None


def verify_skills(skills: list[SkillEvidence], resume_text: str) -> list[SkillEvidence]:
    """Keep only skills whose name or evidence is actually present in the resume text."""
    text_l = " ".join(resume_text.lower().split())
    taxonomy = {s.name.lower(): s for s in SKILLS}
    kept = []
    for s in skills:
        ev = " ".join(s.evidence.lower().split())
        aliases = taxonomy[s.name.lower()].aliases if s.name.lower() in taxonomy else (s.name.lower(),)
        if (ev and ev in text_l) or any(_alias_hit(a, text_l) >= 0 for a in aliases):
            if s.topic not in TOPICS:
                s = s.model_copy(update={"topic": taxonomy[s.name.lower()].topic if s.name.lower() in taxonomy else "algorithms"})
            kept.append(s)
    return kept


@register_handler("resume_analysis")
def rule_analysis(ctx: dict[str, Any]) -> ResumeAnalysis:
    resume = ctx.get("resume_text", "") or ""
    jd = ctx.get("jd_text", "") or ""
    role = get_role(ctx.get("role_key", "software_engineer"))
    resume_skills = extract_skills(resume)
    jd_skills = extract_skills(jd) if jd.strip() else []
    if jd_skills:
        requirements = [s.name for s in jd_skills]
        req_topics = [s.topic for s in jd_skills]
    else:
        requirements = [topic_label(t) for t in role.topic_weights]
        req_topics = list(role.topic_weights)
    have_topics = {s.topic for s in resume_skills}
    have_names = {s.name for s in resume_skills}
    gaps = [r for r, t in zip(requirements, req_topics, strict=False) if r not in have_names and t not in have_topics]
    years = estimate_years(resume) if resume else None
    declared = ctx.get("declared_experience")
    if years is None and isinstance(declared, (int, float)):
        years = float(declared)
    level = level_for_years(years, role.default_experience)
    role_topics = sorted(role.topic_weights, key=lambda t: -role.topic_weights[t])
    priority = [t for t in dict.fromkeys(req_topics) if t in role.topic_weights or t in TOPICS][:8]
    interview_topics = list(dict.fromkeys(priority + role_topics))[:10]
    diff = {"entry": 1, "junior": 1, "mid": 2, "senior": 3, "lead": 3}[level]
    if ctx.get("preferred_difficulty") in ("easy", "medium", "hard"):
        difficulty = ctx["preferred_difficulty"]
    else:
        difficulty = LEVEL_NAME[max(1, min(3, diff + (1 if years and years >= 2 else 0)))]
    profile_bits = []
    if years is not None:
        profile_bits.append(f"{years:g} years of stated experience")
    if resume_skills:
        profile_bits.append("skills in " + ", ".join(s.name for s in resume_skills[:6]))
    profile = ("Candidate with " + " and ".join(profile_bits) + ".") if profile_bits else "No resume provided; using role defaults."
    notes = []
    if not resume.strip():
        notes.append("No resume text was available; questions are based on the role only.")
    if not jd.strip():
        notes.append("No job description provided; requirements come from the role profile.")
    return ResumeAnalysis(
        candidate_name=guess_name(resume) if resume else None,
        candidate_profile=profile,
        target_role=role.title,
        experience_level=level,  # type: ignore[arg-type]
        years_experience=years,
        skills=resume_skills,
        technologies=[s.name for s in resume_skills],
        job_requirements=requirements,
        skill_gaps=gaps,
        priority_topics=priority,
        interview_topics=interview_topics,
        question_difficulty=difficulty,  # type: ignore[arg-type]
        notes=notes,
    )


async def analyze(
    ai: AIClient,
    resume_text: str,
    jd_text: str,
    role_key: str,
    declared_experience: float | None = None,
    preferred_difficulty: str | None = None,
) -> tuple[ResumeAnalysis, Any]:
    role = get_role(role_key)
    ctx = {
        "resume_text": resume_text,
        "jd_text": jd_text,
        "role_key": role.key,
        "declared_experience": declared_experience,
        "preferred_difficulty": preferred_difficulty,
    }
    prompt = (
        f"Target role: {role.title} — {role.description}\n"
        f"Role topics: {', '.join(role.topic_weights)}\n"
        f"Candidate-declared years of experience: {declared_experience}\n"
        f"<resume>\n{resume_text[:30000] or '(none provided)'}\n</resume>\n"
        f"<job_description>\n{jd_text[:15000] or '(none provided)'}\n</job_description>"
    )
    result = await ai.run(
        AIRequest(
            task="resume_analysis",
            schema=ResumeAnalysis,
            system=ANALYSIS_SYSTEM.format(topics=", ".join(TOPICS)),
            prompt=prompt,
            context=ctx,
            effort="medium",
        )
    )
    a = result.output
    # Deterministic guardrails on LLM output
    a = a.model_copy(
        update={
            "skills": verify_skills(a.skills, resume_text),
            "priority_topics": [t for t in a.priority_topics if t in TOPICS],
            "interview_topics": [t for t in a.interview_topics if t in TOPICS] or list(role.topic_weights),
            "target_role": role.title,
        }
    )
    a = a.model_copy(update={"technologies": [s.name for s in a.skills]})
    if preferred_difficulty in ("easy", "medium", "hard"):
        a = a.model_copy(update={"question_difficulty": preferred_difficulty})
    return a, result


__all__ = ["ROLES", "analyze", "extract_skills", "rule_analysis", "verify_skills"]
