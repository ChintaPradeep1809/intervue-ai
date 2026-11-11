from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CATEGORIES: dict[str, str] = {
    "technical_correctness": "Technical correctness",
    "problem_solving": "Problem solving",
    "communication": "Communication",
    "code_quality": "Code quality",
    "architecture": "Architecture",
    "tradeoffs": "Trade-offs",
    "debugging": "Debugging",
    "depth_of_knowledge": "Depth of knowledge",
    "time_management": "Time management",
}


class ExpectedConcept(BaseModel):
    name: str
    keywords: list[str]


class Evidence(BaseModel):
    source: Literal["transcript", "code", "execution", "design"]
    kind: Literal["quote", "absence", "measurement"] = "quote"
    quote: str = Field(default="", description="Verbatim excerpt from the source; empty for absence/measurement")
    observation: str
    polarity: Literal["positive", "negative"]


class CategoryScore(BaseModel):
    category: str
    score: int = Field(ge=0, le=100)


class AnswerScore(BaseModel):
    score: int = Field(ge=0, le=100)
    categories: list[CategoryScore]
    covered_concepts: list[str]
    missing_concepts: list[str]
    evidence: list[Evidence]
    strengths: list[str]
    weaknesses: list[str]
    summary: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)


class CodeFailure(BaseModel):
    name: str
    input: str
    expected: str
    actual: str


class CodeSubmissionSummary(BaseModel):
    language: str
    code: str
    problem_id: str
    problem_title: str
    passed: int
    total: int
    status: Literal["passed", "failed", "error", "timeout"]
    error: str | None = None
    runtime_ms: int = 0
    run_count: int = 1
    failures: list[CodeFailure] = Field(default_factory=list)
    expected_features: list[str] = Field(default_factory=list)


class DesignNode(BaseModel):
    id: str
    kind: str
    label: str


class DesignEdge(BaseModel):
    source: str
    target: str
    label: str = ""


class DesignSummary(BaseModel):
    nodes: list[DesignNode] = Field(default_factory=list)
    edges: list[DesignEdge] = Field(default_factory=list)
    notes: str = ""

    def as_text(self) -> str:
        if not self.nodes:
            return ""
        by_id = {n.id: n for n in self.nodes}
        comps = ", ".join(f"{n.label} ({n.kind})" for n in self.nodes)
        flows = "; ".join(
            f"{by_id[e.source].label} -> {by_id[e.target].label}" + (f" [{e.label}]" if e.label else "")
            for e in self.edges
            if e.source in by_id and e.target in by_id
        )
        text = f"Components: {comps}."
        if flows:
            text += f" Data flow: {flows}."
        if self.notes.strip():
            text += f" Notes: {self.notes.strip()}"
        return text


class TopicScore(BaseModel):
    topic: str
    label: str
    score: int
    answered: int


class QuestionAnalysis(BaseModel):
    question: str
    topic: str
    kind: str
    score: int
    summary: str
    covered: list[str]
    missing: list[str]


class PracticeStep(BaseModel):
    day: str
    focus: str
    activities: list[str]


class ReportNarrative(BaseModel):
    headline: str
    strongest_area: str
    main_weakness: str
    summary: str
    recommendations: list[str]


class Report(BaseModel):
    overall_score: int
    section_scores: list[CategoryScore]  # technical, communication, problem_solving, coding, system_design
    category_scores: list[CategoryScore]  # the nine evaluation categories
    category_evidence: dict[str, list[Evidence]]
    role_readiness: Literal["ready", "nearly_ready", "developing", "not_yet_ready", "insufficient_data"]
    readiness_label: str
    topic_scores: list[TopicScore]
    strong_areas: list[str]
    weak_areas: list[str]
    questions_missed: list[QuestionAnalysis]
    recommended_topics: list[str]
    practice_plan: list[PracticeStep]
    question_analysis: list[QuestionAnalysis]
    coding_summary: list[dict[str, object]]
    transcript_summary: str
    narrative: ReportNarrative
    answered_count: int
    disclaimer: str
