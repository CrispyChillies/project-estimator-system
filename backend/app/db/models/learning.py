import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ARRAY, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import enums as E
from app.db.base import Base, IdMixin, TimestampMixin, enum_check

FK = lambda target: ForeignKey(target, ondelete="CASCADE")  # noqa: E731


class TaskActual(IdMixin, TimestampMixin, Base):
    __tablename__ = "task_actuals"
    __table_args__ = (enum_check("task_actuals", "source", E.ACTUAL_SOURCE),)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("tasks.id"), unique=True)
    actual_hours: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(10), default="manual")
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text, default="")


class UnplannedActual(IdMixin, TimestampMixin, Base):
    __tablename__ = "unplanned_actuals"
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("task_categories.id"))
    hours: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(Text, default="")


class CalibrationStat(IdMixin, TimestampMixin, Base):
    __tablename__ = "calibration_stats"
    __table_args__ = (
        enum_check("calibration_stats", "layer", E.LAYER),
        enum_check("calibration_stats", "scope_type", E.SCOPE_TYPE),
        Index("ux_calibration_stats_scope", "layer", "scope_type", "scope_key", unique=True),
    )
    layer: Mapped[str] = mapped_column(String(10))
    scope_type: Mapped[str] = mapped_column(String(20))
    scope_key: Mapped[str] = mapped_column(String(200))
    n: Mapped[int] = mapped_column(Integer, default=0)
    mean_log_ratio: Mapped[float] = mapped_column(Float, default=0)
    var_log_ratio: Mapped[float] = mapped_column(Float, default=0)
    shrunk_mean: Mapped[float] = mapped_column(Float, default=0)
    shrunk_var: Mapped[float] = mapped_column(Float, default=0.25)
    residuals: Mapped[list[float]] = mapped_column(JSONB, default=list)


class CalibrationRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "calibration_runs"
    __table_args__ = (
        enum_check("calibration_runs", "trigger", E.RUN_TRIGGER),
    )
    trigger: Mapped[str] = mapped_column(String(30))
    layer: Mapped[str] = mapped_column(String(10))
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"))
    stats_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class LearnedRule(IdMixin, TimestampMixin, Base):
    __tablename__ = "learned_rules"
    __table_args__ = (
        enum_check("learned_rules", "status", E.RULE_STATUS),
        enum_check("learned_rules", "layer", E.LAYER),
    )
    text: Mapped[str] = mapped_column(Text)
    layer: Mapped[str] = mapped_column(String(10))
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence_event_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default="proposed")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class LLMCall(IdMixin, TimestampMixin, Base):
    __tablename__ = "llm_calls"
    purpose: Mapped[str] = mapped_column(String(60), index=True)
    model: Mapped[str] = mapped_column(String(80))
    prompt_hash: Mapped[str] = mapped_column(String(64), index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    request: Mapped[Any] = mapped_column(JSONB, nullable=True)
    response: Mapped[Any] = mapped_column(JSONB, nullable=True)


class LLMRawEstimate(IdMixin, TimestampMixin, Base):
    __tablename__ = "llm_raw_estimates"
    __table_args__ = (Index("ix_llm_raw_project_key", "project_id", "task_key"),)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("projects.id"))
    task_key: Mapped[str] = mapped_column(String(80))
    run_idx: Mapped[int] = mapped_column(Integer)
    prompt_version: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    raw_min: Mapped[float] = mapped_column(Float)
    raw_max: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class BacktestRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "backtest_runs"
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="queued")
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class BacktestResult(IdMixin, TimestampMixin, Base):
    __tablename__ = "backtest_results"
    __table_args__ = (enum_check("backtest_results", "level", E.BACKTEST_LEVEL),)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("backtest_runs.id"), index=True)
    estimator_key: Mapped[str] = mapped_column(String(40))
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), FK("projects.id"))
    task_key: Mapped[str | None] = mapped_column(String(80))
    level: Mapped[str] = mapped_column(String(10))
    n_train: Mapped[int] = mapped_column(Integer)
    predicted_p50: Mapped[float] = mapped_column(Float)
    predicted_p80: Mapped[float] = mapped_column(Float)
    actual: Mapped[float] = mapped_column(Float)
    ape: Mapped[float] = mapped_column(Float)
    covered_p80: Mapped[bool] = mapped_column(Boolean)
    interval_width: Mapped[float] = mapped_column(Float)


class Job(IdMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (enum_check("jobs", "status", E.JOB_STATUS),)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(10), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text)
    result_ref: Mapped[str | None] = mapped_column(String(200))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
