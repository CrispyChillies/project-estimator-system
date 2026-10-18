"""Analog (case-based) retrieval over tasks of OTHER projects with a final estimate."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Estimate, Module, Project, Task, TaskActual, TaskAIBaseline, TaskCategory
from app.services.calibration import Analog, mid


@dataclass
class Candidate:
    analog: Analog
    category: str


def select_analogs(cands: Sequence[Candidate], category: str, top_k: int) -> list[Analog]:
    """`cands` sorted by similarity desc. Prefer same-category when >= 3 candidates exist."""
    same = [c for c in cands if c.category == category]
    pool = same if len(same) >= 3 else list(cands)
    return [c.analog for c in pool[:top_k]]


def find_analogs(db: Session, embedding: Sequence[float], category: str, *, exclude_project_id: uuid.UUID | None,
                 allowed_project_ids: Iterable[uuid.UUID] | None = None, top_k: int = 5) -> list[Analog]:
    dist = Task.embedding.cosine_distance(list(embedding)).label("dist")
    q = (
        select(Task, Project.id, Project.name, TaskCategory.key, TaskAIBaseline.raw_min, TaskAIBaseline.raw_max,
               TaskActual.actual_hours, dist)
        .join(Estimate, Estimate.id == Task.estimate_id)
        .join(Project, Project.id == Estimate.project_id)
        .join(Module, Module.id == Task.module_id)
        .outerjoin(TaskCategory, TaskCategory.id == Task.category_id)
        .outerjoin(TaskAIBaseline, TaskAIBaseline.task_id == Task.id)
        .outerjoin(TaskActual, TaskActual.task_id == Task.id)
        .where(Estimate.status == "final", Task.enabled.is_(True), Task.removed.is_(False),
               Module.removed.is_(False), Task.embedding.is_not(None))
        .order_by(dist)
        .limit(top_k * 6)
    )
    if exclude_project_id is not None:
        q = q.where(Project.id != exclude_project_id)
    if allowed_project_ids is not None:
        q = q.where(Project.id.in_(list(allowed_project_ids)))
    cands = []
    for t, pid, pname, cat, rmin, rmax, actual, d in db.execute(q):
        cands.append(Candidate(Analog(
            task_id=str(t.id), project_id=str(pid), project_name=pname, title=t.title,
            similarity=float(1 - d), raw_mid=mid(rmin, rmax) if rmin is not None else None,
            final_mid=mid(t.min_hours, t.max_hours), actual_mid=actual,
        ), cat or "other"))
    return select_analogs(cands, category, top_k)


def cosine_rank(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Similarities of a query against rows of `matrix` (both L2-normalised or not)."""
    qn = query / (np.linalg.norm(query) or 1.0)
    mn = matrix / np.clip(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12, None)
    return mn @ qn
