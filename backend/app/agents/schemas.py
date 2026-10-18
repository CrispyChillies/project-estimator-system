from typing import Literal

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    id: str
    text: str
    type: Literal["functional", "non_functional", "constraint"] = "functional"
    source_chunk_ids: list[str] = Field(default_factory=list)


class ScenarioTask(BaseModel):
    title: str
    category_key: str
    role_name: str
    min_hours: float
    max_hours: float


class Unknown(BaseModel):
    question: str
    why_it_matters: str
    affected_requirement_ids: list[str] = Field(default_factory=list)
    scenario_if_yes: list[ScenarioTask] = Field(default_factory=list)
    prior_probability: float = Field(0.5, ge=0, le=1)


class ExtractionResult(BaseModel):
    summary: str
    requirements: list[Requirement]
    ambiguities: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    unknowns: list[Unknown] = Field(default_factory=list)


class DecomposedTask(BaseModel):
    key: str
    title: str
    description: str
    category_key: str
    role_name: str
    rationale: str
    requirement_ids: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"


class DecomposedModule(BaseModel):
    name: str
    description: str = ""
    tasks: list[DecomposedTask]


class Decomposition(BaseModel):
    modules: list[DecomposedModule]


class TaskHours(BaseModel):
    task_key: str
    min_hours: float = Field(ge=0)
    max_hours: float = Field(ge=0)


class EstimationResult(BaseModel):
    estimates: list[TaskHours]


class Lesson(BaseModel):
    text: str
    layer: Literal["edit", "actual"]
    category_key: str | None = None
    evidence_count: int = 0


class LessonsResult(BaseModel):
    rules: list[Lesson]
