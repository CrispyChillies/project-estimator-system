import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import enums as E
from app.db.base import Base, IdMixin, TimestampMixin, enum_check
from app.db.models.project import DIM

FK = lambda target: ForeignKey(target, ondelete="CASCADE")  # noqa: E731


class Estimate(IdMixin, TimestampMixin, Base):
    __tablename__ = "estimates"
    __table_args__ = (
        enum_check("estimates", "status", E.ESTIMATE_STATUS),
        enum_check("estimates", "source", E.ESTIMATE_SOURCE),
        UniqueConstraint("project_id", "version", name="uq_estimates_project_version"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("projects.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(10), default="draft")
    source: Mapped[str] = mapped_column(String(10), default="ai")
    learning_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    model_key: Mapped[str] = mapped_column(String(160), default="fake-v1", index=True)
    model_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    parent_estimate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimates.id", ondelete="SET NULL")
    )


class Module(IdMixin, TimestampMixin, Base):
    __tablename__ = "modules"
    estimate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("estimates.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    removed: Mapped[bool] = mapped_column(Boolean, default=False)


class Task(IdMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        enum_check("tasks", "confidence", E.CONFIDENCE),
        enum_check("tasks", "origin", E.ORIGIN),
        Index("ix_tasks_embedding", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )
    estimate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("estimates.id"), index=True)
    module_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("modules.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("task_categories.id"))
    delivery_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("delivery_roles.id")
    )
    min_hours: Mapped[float] = mapped_column(Float, default=0)
    max_hours: Mapped[float] = mapped_column(Float, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    removed: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[str] = mapped_column(String(10), default="medium")
    rationale: Mapped[str] = mapped_column(Text, default="")
    source_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    origin: Mapped[str] = mapped_column(String(10), default="ai")
    ai_key: Mapped[str | None] = mapped_column(String(80), index=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(DIM))


class TaskAIBaseline(IdMixin, TimestampMixin, Base):
    """Immutable snapshot written at generation time. Never updated."""

    __tablename__ = "task_ai_baselines"
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("tasks.id"), unique=True)
    estimate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("estimates.id"), index=True)
    ai_key: Mapped[str] = mapped_column(String(80))
    raw_min: Mapped[float] = mapped_column(Float)
    raw_max: Mapped[float] = mapped_column(Float)
    analog_mid: Mapped[float | None] = mapped_column(Float)
    analog_task_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    calibrated_min: Mapped[float | None] = mapped_column(Float)
    calibrated_max: Mapped[float | None] = mapped_column(Float)
    applied_factor: Mapped[float] = mapped_column(Float, default=1.0)
    # displayed values at generation time (= calibrated when learning on, else raw)
    shown_min: Mapped[float] = mapped_column(Float)
    shown_max: Mapped[float] = mapped_column(Float)
    category_key: Mapped[str] = mapped_column(String(60), default="other")
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    prompt_version: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    model_key: Mapped[str] = mapped_column(String(160), default="fake-v1")


class Assumption(IdMixin, TimestampMixin, Base):
    __tablename__ = "assumptions"
    __table_args__ = (enum_check("assumptions", "kind", E.ASSUMPTION_KIND),)
    estimate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("estimates.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    source_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)


class ClarifyingQuestion(IdMixin, TimestampMixin, Base):
    __tablename__ = "clarifying_questions"
    __table_args__ = (enum_check("clarifying_questions", "status", E.QUESTION_STATUS),)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("projects.id"), index=True)
    estimate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("estimates.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str] = mapped_column(Text, default="")
    affected_task_keys: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    scenario_tasks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    scenario_delta_min: Mapped[float] = mapped_column(Float, default=0)
    scenario_delta_max: Mapped[float] = mapped_column(Float, default=0)
    prior_probability: Mapped[float] = mapped_column(Float, default=0.5)
    impact_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="open")
    answer: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EditEvent(IdMixin, Base):
    """Append-only. Never updated or deleted (enforced by a DB trigger)."""

    __tablename__ = "edit_events"
    __table_args__ = (
        enum_check("edit_events", "actor", E.ACTOR),
        enum_check("edit_events", "event_type", E.EVENT_TYPES),
        Index("ix_edit_events_estimate_created", "estimate_id", "created_at"),
    )
    estimate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("estimates.id"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), FK("tasks.id"), index=True)
    module_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), FK("modules.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    actor: Mapped[str] = mapped_column(String(10))
    event_type: Mapped[str] = mapped_column(String(40))
    field: Mapped[str | None] = mapped_column(String(60))
    old_value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    reason_tag: Mapped[str | None] = mapped_column(String(40))
    reason_text: Mapped[str | None] = mapped_column(Text)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )


class ChangeProposal(IdMixin, TimestampMixin, Base):
    __tablename__ = "change_proposals"
    __table_args__ = (enum_check("change_proposals", "status", E.PROPOSAL_STATUS),)
    estimate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("estimates.id"), index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), FK("agent_sessions.id"))
    status: Mapped[str] = mapped_column(String(10), default="pending")
    ops: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    rationale: Mapped[str] = mapped_column(Text, default="")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentSession(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (enum_check("agent_sessions", "mode", E.AGENT_MODE),)
    estimate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("estimates.id"), index=True)
    mode: Mapped[str] = mapped_column(String(10), default="chat")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class AgentMessage(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_messages"
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("agent_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text, default="")
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
