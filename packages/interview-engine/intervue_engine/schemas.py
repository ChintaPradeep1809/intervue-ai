from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Phase(StrEnum):
    INTERVIEW_SETUP = "INTERVIEW_SETUP"
    INTRODUCTION = "INTRODUCTION"
    TECHNICAL_QUESTION = "TECHNICAL_QUESTION"
    FOLLOW_UP = "FOLLOW_UP"
    CODING = "CODING"
    CODE_REVIEW = "CODE_REVIEW"
    SYSTEM_DESIGN = "SYSTEM_DESIGN"
    BEHAVIORAL = "BEHAVIORAL"
    FINAL_EVALUATION = "FINAL_EVALUATION"
    COMPLETED = "COMPLETED"


class NextAction(StrEnum):
    START = "START"
    WAIT_FOR_ANSWER = "WAIT_FOR_ANSWER"
    WAIT_FOR_CODE = "WAIT_FOR_CODE"
    GENERATE_REPORT = "GENERATE_REPORT"
    NONE = "NONE"


RoundKind = Literal["introduction", "technical", "coding", "sql", "system_design", "behavioral"]
Difficulty = Literal["easy", "medium", "hard"]
LEVEL = {"easy": 1, "medium": 2, "hard": 3}
LEVEL_NAME = {1: "easy", 2: "medium", 3: "hard"}
ExperienceLevel = Literal["entry", "junior", "mid", "senior", "lead"]


# ---------------------------------------------------------------- resume / JD analysis
class SkillEvidence(BaseModel):
    name: str
    topic: str
    evidence: str = Field(description="Verbatim snippet from the resume that mentions this skill")


class ResumeAnalysis(BaseModel):
    candidate_name: str | None
    candidate_profile: str
    target_role: str
    experience_level: ExperienceLevel
    years_experience: float | None
    skills: list[SkillEvidence]
    technologies: list[str]
    job_requirements: list[str]
    skill_gaps: list[str]
    priority_topics: list[str]
    interview_topics: list[str]
    question_difficulty: Difficulty
    notes: list[str]


# ---------------------------------------------------------------- plan
class PlanRound(BaseModel):
    id: str
    kind: RoundKind
    title: str
    topics: list[str]
    minutes: int
    question_count: int
    language: str | None = None  # coding rounds


class SkillWeight(BaseModel):
    topic: str
    label: str
    weight: float


class InterviewPlan(BaseModel):
    role_key: str
    role_title: str
    experience_level: ExperienceLevel
    difficulty: Difficulty
    interview_type: str
    duration_minutes: int
    rounds: list[PlanRound]
    skill_weights: list[SkillWeight]
    total_questions: int
    rationale: list[str]
    personalized_from_resume: bool = False


# ---------------------------------------------------------------- state
class AskedQuestion(BaseModel):
    qid: str  # bank id, generated id, or problem id
    db_id: str | None = None
    round_id: str
    topic: str
    text: str
    difficulty: int
    kind: Literal["primary", "followup", "coding", "code_review", "design"]
    followup_type: str | None = None
    parent_qid: str | None = None
    expected_concepts: list[dict[str, Any]] = Field(default_factory=list)
    asked_at: float


class ScoreEntry(BaseModel):
    qid: str
    topic: str
    kind: str
    score: int


class CodeState(BaseModel):
    problem_id: str
    language: str
    is_sql: bool
    code: str = ""
    run_count: int = 0
    submitted: bool = False
    last_result: dict[str, Any] | None = None


class InterviewState(BaseModel):
    interview_id: str
    candidate_id: str
    role: str
    phase: Phase = Phase.INTERVIEW_SETUP
    round_index: int = -1
    current_round: str | None = None
    current_question: AskedQuestion | None = None
    question_index: int = 0  # primary questions asked in current round
    followups_for_current: int = 0
    difficulty: int = 2
    asked_question_ids: list[str] = Field(default_factory=list)
    used_followups: list[str] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    code_state: CodeState | None = None
    execution_results: list[dict[str, Any]] = Field(default_factory=list)
    score_history: list[ScoreEntry] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    started_at: float | None = None
    round_started_at: float | None = None
    deadline_at: float | None = None
    ended_at: float | None = None
    rounds_completed: int = 0
    next_action: NextAction = NextAction.START
    context_summary: str = ""  # rolling compact summary instead of resending the full transcript
    utterance_count: int = 0
    personalized_topics: list[str] = Field(default_factory=list)
    end_reason: str | None = None

    def time_remaining(self, now: float) -> float | None:
        return None if self.deadline_at is None else max(0.0, self.deadline_at - now)


# ---------------------------------------------------------------- AI task outputs
class FollowUpDecision(BaseModel):
    should_follow_up: bool
    type: Literal["clarification", "challenge", "edge_case", "optimization", "architecture", "behavioral"]
    question: str
    reason: str
    expected_concepts: list[str]
    difficulty: Difficulty


class PersonalizedQuestion(BaseModel):
    text: str
    referenced_skill: str | None = Field(description="Resume skill referenced in the text, or null")


class CodeReviewQuestion(BaseModel):
    question: str
    focus: Literal["failing_tests", "complexity", "edge_cases", "optimization", "readability", "debugging"]
    expected_concepts: list[str]
