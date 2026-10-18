from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORM):
    id: uuid.UUID
    name: str
    email: str
    role: str


class RoleOut(ORM):
    id: uuid.UUID
    name: str
    hourly_rate: float
    currency: str
    color: str


class RoleUpdate(BaseModel):
    hourly_rate: float = Field(ge=0, le=10_000)
    currency: str = Field(min_length=3, max_length=3)
    color: str | None = None


class CategoryOut(ORM):
    id: uuid.UUID
    key: str
    name: str
    description: str


class CategoryUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field("", max_length=500)


ProjectStatus = Literal["draft", "quoted", "won", "lost", "delivered"]


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    client_name: str = Field("", max_length=200)
    domain: str = Field("", max_length=100)
    tech_tags: list[str] = Field(default_factory=list)
    description: str = Field("", max_length=5000)


class ProjectPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    client_name: str | None = None
    domain: str | None = None
    tech_tags: list[str] | None = None
    description: str | None = None
    status: ProjectStatus | None = None


class ProjectOut(ORM):
    id: uuid.UUID
    name: str
    client_name: str
    domain: str
    tech_tags: list[str]
    description: str
    status: str
    data_source: str
    started_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime


class ProjectListItem(ProjectOut):
    p50_hours: float | None = None
    p80_hours: float | None = None
    final_mid_hours: float | None = None
    actual_hours: float | None = None
    accuracy_pct: float | None = None
    estimate_count: int = 0


class DocumentOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    filename: str
    mime: str
    created_at: datetime
    chars: int = 0
    chunk_count: int = 0


class PasteIn(BaseModel):
    title: str = Field("pasted-brief", max_length=200)
    text: str = Field(min_length=20, max_length=200_000)


class ChunkOut(ORM):
    id: uuid.UUID
    idx: int
    text: str


class GenerateIn(BaseModel):
    document_ids: list[uuid.UUID] = Field(default_factory=list)
    learning: bool = True


class JobOut(ORM):
    id: uuid.UUID
    kind: str
    status: str
    progress: float
    message: str
    error: str | None
    result_ref: str | None
    created_at: datetime


class EstimateOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    version: int
    status: str
    source: str
    learning_enabled: bool
    model_snapshot: dict[str, Any]
    summary: dict[str, Any]
    finalized_at: datetime | None
    parent_estimate_id: uuid.UUID | None
    created_at: datetime


class BaselineOut(ORM):
    raw_min: float
    raw_max: float
    analog_mid: float | None
    calibrated_min: float | None
    calibrated_max: float | None
    applied_factor: float
    shown_min: float
    shown_max: float
    provenance: dict[str, Any]
    prompt_version: str
    model: str


class TaskOut(ORM):
    id: uuid.UUID
    module_id: uuid.UUID
    title: str
    description: str
    category_id: uuid.UUID | None
    delivery_role_id: uuid.UUID | None
    min_hours: float
    max_hours: float
    position: int
    enabled: bool
    removed: bool
    confidence: str
    rationale: str
    origin: str
    ai_key: str | None
    source_chunk_ids: list[uuid.UUID]
    baseline: BaselineOut | None = None
    delta_pct: float | None = None
    actual_hours: float | None = None
    comment_count: int = 0


class ModuleOut(ORM):
    id: uuid.UUID
    name: str
    description: str
    position: int
    removed: bool
    tasks: list[TaskOut] = Field(default_factory=list)


class EstimateTree(BaseModel):
    estimate: EstimateOut
    modules: list[ModuleOut]


ReasonTag = Literal["underestimated_complexity", "overestimated", "reuse_existing_code", "client_specific",
                    "scope_added", "scope_removed", "risk_buffer", "other"]


class TaskCreate(BaseModel):
    module_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    category_id: uuid.UUID | None = None
    delivery_role_id: uuid.UUID | None = None
    min_hours: float = Field(0, ge=0, le=10_000)
    max_hours: float = Field(0, ge=0, le=10_000)
    reason_tag: ReasonTag | None = None
    reason_text: str | None = Field(None, max_length=1000)


class TaskPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = None
    category_id: uuid.UUID | None = None
    delivery_role_id: uuid.UUID | None = None
    min_hours: float | None = Field(None, ge=0, le=10_000)
    max_hours: float | None = Field(None, ge=0, le=10_000)
    enabled: bool | None = None
    confidence: Literal["low", "medium", "high"] | None = None
    module_id: uuid.UUID | None = None
    position: int | None = None
    reason_tag: ReasonTag | None = None
    reason_text: str | None = Field(None, max_length=1000)


class ReasonIn(BaseModel):
    reason_tag: ReasonTag | None = None
    reason_text: str | None = Field(None, max_length=1000)


class ModuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ModulePatch(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ReorderIn(BaseModel):
    module_id: uuid.UUID
    task_ids: list[uuid.UUID]


class BulkIn(BaseModel):
    task_ids: list[uuid.UUID]
    enabled: bool | None = None
    percent: float | None = Field(None, ge=-90, le=500)
    reason_tag: ReasonTag | None = None


class EditEventOut(ORM):
    id: uuid.UUID
    estimate_id: uuid.UUID
    task_id: uuid.UUID | None
    module_id: uuid.UUID | None
    user_id: uuid.UUID | None
    actor: str
    event_type: str
    field: str | None
    old_value: Any
    new_value: Any
    reason_tag: str | None
    reason_text: str | None
    proposal_id: uuid.UUID | None
    created_at: datetime
    task_title: str | None = None
    user_name: str | None = None


class ProposalOut(ORM):
    id: uuid.UUID
    estimate_id: uuid.UUID
    session_id: uuid.UUID | None
    status: str
    ops: list[dict[str, Any]]
    rationale: str
    created_at: datetime


class AgentMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    session_id: uuid.UUID | None = None


class AgentMessageOut(ORM):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class QuestionOut(ORM):
    id: uuid.UUID
    estimate_id: uuid.UUID
    question: str
    why_it_matters: str
    affected_task_keys: list[str]
    scenario_tasks: list[dict[str, Any]]
    scenario_delta_min: float
    scenario_delta_max: float
    prior_probability: float
    impact_score: float
    status: str
    answer: str | None


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)
    scenario_applies: bool = False


class AnswerOut(BaseModel):
    question: QuestionOut
    proposal: ProposalOut | None


class AssumptionOut(ORM):
    id: uuid.UUID
    kind: str
    text: str
    source_chunk_ids: list[uuid.UUID]


class ActualIn(BaseModel):
    task_id: uuid.UUID
    actual_hours: float = Field(ge=0, le=100_000)
    note: str = Field("", max_length=500)


class ActualRow(BaseModel):
    task_id: uuid.UUID
    module: str
    title: str
    min_hours: float
    max_hours: float
    actual_hours: float | None
    note: str | None


class UnplannedIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    hours: float = Field(gt=0, le=100_000)
    category_id: uuid.UUID | None = None
    note: str = ""


class UnplannedOut(ORM):
    id: uuid.UUID
    title: str
    hours: float
    category_id: uuid.UUID | None
    note: str


class RuleOut(ORM):
    id: uuid.UUID
    text: str
    layer: str
    scope: dict[str, Any]
    evidence_event_ids: list[uuid.UUID]
    evidence_count: int
    status: str
    created_at: datetime


class RuleStatusIn(BaseModel):
    status: Literal["active", "disabled", "proposed"]


class BacktestIn(BaseModel):
    protocol: Literal["loo", "chronological"] = "loo"
    data_source: Literal["synthetic", "dataset"] = "synthetic"


class BacktestRunOut(ORM):
    id: uuid.UUID
    config: dict[str, Any]
    status: str
    summary: dict[str, Any]
    created_at: datetime


class BacktestDetail(BaseModel):
    run: BacktestRunOut
    projects: list[dict[str, Any]]


class LLMUsage(BaseModel):
    calls: int
    cache_hits: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    mode: str
    model: str
    embedding_model: str
    by_purpose: list[dict[str, Any]]


class CompareRow(BaseModel):
    ai_key: str | None
    title: str
    category: str | None
    a_min: float | None
    a_max: float | None
    b_min: float | None
    b_max: float | None
    factor: float | None


class CompareOut(BaseModel):
    a: EstimateOut
    b: EstimateOut
    rows: list[CompareRow]
