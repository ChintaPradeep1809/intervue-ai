"""SQLAlchemy models. Every organisation-scoped row carries `organization_id` and is only read
through tenant-checked queries (see app/deps.py and app/services/tenancy.py)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, JSONType


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# --------------------------------------------------------------------------- identity & tenancy
class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(32), default="candidate", index=True)  # candidate|organization_admin|super_admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile: Mapped[CandidateProfile | None] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="company")  # college|university|institute|bootcamp|company
    settings: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class OrganizationMember(TimestampMixin, Base):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_org_member"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="candidate")  # admin|reviewer|candidate


class CandidateProfile(TimestampMixin, Base):
    __tablename__ = "candidate_profiles"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    experience_years: Mapped[float | None] = mapped_column(Float)
    target_role: Mapped[str | None] = mapped_column(String(64))
    headline: Mapped[str] = mapped_column(String(300), default="")
    location: Mapped[str] = mapped_column(String(120), default="")
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    user: Mapped[User] = relationship(back_populates="profile")


# --------------------------------------------------------------------------- documents
class Resume(TimestampMixin, Base):
    __tablename__ = "resumes"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(200))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")


class JobDescription(TimestampMixin, Base):
    __tablename__ = "job_descriptions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16), default="paste")  # paste|upload
    storage_key: Mapped[str | None] = mapped_column(String(300))


# --------------------------------------------------------------------------- templates & questions
class InterviewTemplate(TimestampMixin, Base):
    __tablename__ = "interview_templates"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    role_key: Mapped[str] = mapped_column(String(64))
    experience_level: Mapped[str] = mapped_column(String(16), default="junior")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=45)
    difficulty: Mapped[str] = mapped_column(String(16), default="medium")
    interview_type: Mapped[str] = mapped_column(String(32), default="full")
    rounds: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    topics: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    scoring_weights: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    jd_text: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Question(TimestampMixin, Base):
    """Question bank. organization_id NULL = platform-wide."""

    __tablename__ = "questions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    bank_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    topic: Mapped[str] = mapped_column(String(40), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="technical")
    difficulty: Mapped[int] = mapped_column(Integer, default=2)
    text: Mapped[str] = mapped_column(Text)
    concepts: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    followups: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    roles: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Invite(TimestampMixin, Base):
    __tablename__ = "invites"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_templates.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(200), default="")
    max_uses: Mapped[int] = mapped_column(Integer, default=100)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_domain: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


# --------------------------------------------------------------------------- interviews
class Interview(TimestampMixin, Base):
    __tablename__ = "interviews"
    __table_args__ = (
        Index("ix_interviews_org_status", "organization_id", "status"),
        Index("ix_interviews_candidate_created", "candidate_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interview_templates.id", ondelete="SET NULL"))
    invite_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invites.id", ondelete="SET NULL"))
    resume_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))
    jd_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job_descriptions.id", ondelete="SET NULL"))
    role_key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    interview_type: Mapped[str] = mapped_column(String(32), default="full")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=45)
    difficulty: Mapped[str] = mapped_column(String(16), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="planned", index=True)  # planned|in_progress|evaluating|completed|abandoned
    plan: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    analysis: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    state: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    consent: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    overall_score: Mapped[int | None] = mapped_column(Integer)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|shortlisted|on_hold|rejected
    reviewer_notes: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InterviewRound(TimestampMixin, Base):
    __tablename__ = "interview_rounds"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), index=True)
    round_key: Mapped[str] = mapped_column(String(16))
    ordinal: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    minutes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|active|completed|skipped
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InterviewQuestion(TimestampMixin, Base):
    __tablename__ = "interview_questions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), index=True)
    round_key: Mapped[str] = mapped_column(String(16))
    qid: Mapped[str] = mapped_column(String(120))
    parent_qid: Mapped[str | None] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    followup_type: Mapped[str | None] = mapped_column(String(20))
    topic: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(Integer, default=2)
    expected_concepts: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    sequence: Mapped[int] = mapped_column(Integer, default=0)


class Response(TimestampMixin, Base):
    __tablename__ = "responses"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_questions.id", ondelete="CASCADE"), index=True)
    answer_text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="voice")  # voice|typed|code


class Transcript(TimestampMixin, Base):
    __tablename__ = "transcripts"
    __table_args__ = (Index("ix_transcripts_interview_seq", "interview_id", "sequence"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"))
    speaker: Mapped[str] = mapped_column(String(16))  # interviewer|candidate|system
    kind: Mapped[str] = mapped_column(String(20), default="speech")
    text: Mapped[str] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer)


class CodeSession(TimestampMixin, Base):
    __tablename__ = "code_sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), index=True)
    problem_id: Mapped[str] = mapped_column(String(80))
    language: Mapped[str] = mapped_column(String(20))
    is_sql: Mapped[bool] = mapped_column(Boolean, default=False)
    code: Mapped[str] = mapped_column(Text, default="")
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CodeExecution(TimestampMixin, Base):
    __tablename__ = "code_executions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    code_session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("code_sessions.id", ondelete="CASCADE"), index=True)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # run|submit
    language: Mapped[str] = mapped_column(String(20))
    code: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    passed: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    runtime_ms: Mapped[int] = mapped_column(Integer, default=0)
    backend: Mapped[str] = mapped_column(String(16), default="")


class DesignSession(TimestampMixin, Base):
    __tablename__ = "design_sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), unique=True)
    graph: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ScreenEvent(TimestampMixin, Base):
    __tablename__ = "screen_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(20))  # started|stopped|snapshot|denied
    reason: Mapped[str] = mapped_column(String(40), default="")
    storage_key: Mapped[str | None] = mapped_column(String(300))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    analysis: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class Evaluation(TimestampMixin, Base):
    __tablename__ = "evaluations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interview_questions.id", ondelete="CASCADE"))
    response_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("responses.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))  # answer|code|design
    topic: Mapped[str] = mapped_column(String(40))
    round_kind: Mapped[str] = mapped_column(String(20))
    score: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)  # AnswerScore
    provider: Mapped[str] = mapped_column(String(40), default="")
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)


class Report(TimestampMixin, Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), unique=True)
    overall_score: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


# --------------------------------------------------------------------------- knowledge base (RAG)
class KnowledgeDocument(TimestampMixin, Base):
    __tablename__ = "knowledge_documents"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(32), default="guidelines")  # guidelines|question_bank|topics|role_description
    filename: Mapped[str] = mapped_column(String(200), default="")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)


class KnowledgeChunk(TimestampMixin, Base):
    __tablename__ = "knowledge_chunks"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[Any]] = mapped_column(JSONType, default=list)


# --------------------------------------------------------------------------- billing, usage, audit
class Plan(TimestampMixin, Base):
    __tablename__ = "plans"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    audience: Mapped[str] = mapped_column(String(20), default="candidate")  # candidate|organization
    price_monthly_usd: Mapped[float] = mapped_column(Float, default=0)
    price_monthly_inr: Mapped[float] = mapped_column(Float, default=0)
    limits: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    features: Mapped[list[Any]] = mapped_column(JSONType, default=list)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id"))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrganizationLimit(TimestampMixin, Base):
    __tablename__ = "organization_limits"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True)
    interviews_per_month: Mapped[int | None] = mapped_column(Integer)
    voice_minutes_per_month: Mapped[int | None] = mapped_column(Integer)
    ai_tokens_per_month: Mapped[int | None] = mapped_column(Integer)
    seats: Mapped[int | None] = mapped_column(Integer)


class UsageRecord(TimestampMixin, Base):
    __tablename__ = "usage_records"
    __table_args__ = (Index("ix_usage_org_created", "organization_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    interview_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)  # llm|voice|tts|embedding|execution|storage
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80), default="")
    task: Mapped[str] = mapped_column(String(60), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    quantity: Mapped[float] = mapped_column(Float, default=0)  # seconds | bytes | characters
    cost_usd: Mapped[float] = mapped_column(Float, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)


class CostRecord(TimestampMixin, Base):
    __tablename__ = "cost_records"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), unique=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    llm_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    voice_seconds: Mapped[float] = mapped_column(Float, default=0)
    embedding_tokens: Mapped[int] = mapped_column(Integer, default=0)
    code_execution_seconds: Mapped[float] = mapped_column(Float, default=0)
    storage_bytes: Mapped[int] = mapped_column(Integer, default=0)
    llm_input_cost: Mapped[float] = mapped_column(Float, default=0)
    llm_output_cost: Mapped[float] = mapped_column(Float, default=0)
    voice_cost: Mapped[float] = mapped_column(Float, default=0)
    embedding_cost: Mapped[float] = mapped_column(Float, default=0)
    storage_cost: Mapped[float] = mapped_column(Float, default=0)
    execution_cost: Mapped[float] = mapped_column(Float, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0)
    estimated_cost_inr: Mapped[float] = mapped_column(Float, default=0)
    fx_rate: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AnalyticsEvent(TimestampMixin, Base):
    __tablename__ = "analytics_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    event: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    interview_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), index=True)
    properties: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str] = mapped_column(String(40), default="")
    target_id: Mapped[str] = mapped_column(String(64), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
