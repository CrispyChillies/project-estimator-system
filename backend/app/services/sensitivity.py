"""Clarifying questions ranked by impact; answering creates a reviewable change proposal."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.db.models import ChangeProposal, ClarifyingQuestion
from app.services import proposals as pr


def list_questions(db: Session, estimate_id: uuid.UUID) -> list[ClarifyingQuestion]:
    return list(db.scalars(select(ClarifyingQuestion).where(ClarifyingQuestion.estimate_id == estimate_id)
                           .order_by(ClarifyingQuestion.impact_score.desc())))


def answer(db: Session, question_id: uuid.UUID, answer_text: str, scenario_applies: bool,
           user_id: uuid.UUID | None) -> tuple[ClarifyingQuestion, ChangeProposal | None]:
    q = db.get(ClarifyingQuestion, question_id)
    if q is None:
        raise NotFound("Question")
    q.status = "answered"
    q.answer = answer_text
    q.answered_at = datetime.now(UTC)
    proposal = None
    if scenario_applies and q.scenario_tasks:
        proposal = pr.new_proposal(db, q.estimate_id, None, f"Answer to: {q.question}")
        for s in q.scenario_tasks:
            pr.add_op(db, proposal, "add_task", {**s, "module_name": "Clarifications", "reason_tag": "scope_added"},
                      summary=f"Add '{s['title']}' ({s['min_hours']:.0f}-{s['max_hours']:.0f} h)",
                      rationale=f"Client answered: {answer_text[:200]}", actor="user")
    db.flush()
    return q, proposal


def dismiss(db: Session, question_id: uuid.UUID) -> ClarifyingQuestion:
    q = db.get(ClarifyingQuestion, question_id)
    if q is None:
        raise NotFound("Question")
    q.status = "dismissed"
    db.flush()
    return q
