"""Change proposals: agent tools only append ops here; applying happens on accept via the estimates service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.errors import AppError, Conflict, NotFound
from app.db.models import ChangeProposal, DeliveryRole, Module, Task, TaskCategory
from app.services import estimates as es
from app.services.calibration import round_half
from app.services.reference import category_maps, role_maps


def get_proposal(db: Session, proposal_id: uuid.UUID) -> ChangeProposal:
    p = db.get(ChangeProposal, proposal_id)
    if p is None:
        raise NotFound("Proposal")
    return p


def pending_proposal(db: Session, estimate_id: uuid.UUID, session_id: uuid.UUID | None, rationale: str = "") -> ChangeProposal:
    q = select(ChangeProposal).where(ChangeProposal.estimate_id == estimate_id, ChangeProposal.status == "pending")
    q = q.where(ChangeProposal.session_id == session_id) if session_id else q.where(ChangeProposal.session_id.is_(None))
    p = db.scalars(q.order_by(ChangeProposal.created_at.desc())).first()
    if p is None:
        p = ChangeProposal(estimate_id=estimate_id, session_id=session_id, status="pending", ops=[], rationale=rationale)
        db.add(p)
        db.flush()
    return p


def new_proposal(db: Session, estimate_id: uuid.UUID, session_id: uuid.UUID | None, rationale: str) -> ChangeProposal:
    p = ChangeProposal(estimate_id=estimate_id, session_id=session_id, status="pending", ops=[], rationale=rationale)
    db.add(p)
    db.flush()
    return p


def add_op(db: Session, proposal: ChangeProposal, op_type: str, payload: dict, summary: str, rationale: str = "",
           actor: str = "agent") -> dict:
    es.ensure_draft(db, proposal.estimate_id)
    _validate(db, proposal.estimate_id, op_type, payload)
    op = {"id": uuid.uuid4().hex[:10], "type": op_type, "status": "pending", "payload": payload,
          "summary": summary, "rationale": rationale, "actor": actor}
    proposal.ops = [*proposal.ops, op]
    flag_modified(proposal, "ops")
    db.flush()
    return op


def _task_in(db: Session, estimate_id: uuid.UUID, task_id: str) -> Task:
    t = db.get(Task, uuid.UUID(task_id))
    if t is None or t.estimate_id != estimate_id:
        raise AppError("invalid_task", f"Task {task_id} not in this estimate", 422)
    return t


def _validate(db: Session, estimate_id: uuid.UUID, op_type: str, payload: dict) -> None:
    if op_type in ("update_task", "remove_task", "split_task"):
        _task_in(db, estimate_id, payload["task_id"])
    if op_type == "bulk_adjust":
        for c in payload.get("changes", []):
            _task_in(db, estimate_id, c["task_id"])
    if op_type == "remove_module":
        m = db.get(Module, uuid.UUID(payload["module_id"]))
        if m is None or m.estimate_id != estimate_id:
            raise AppError("invalid_module", "Module not in this estimate", 422)


def bulk_changes(db: Session, estimate_id: uuid.UUID, percent: float, role_name: str | None = None,
                 category_key: str | None = None, module_name: str | None = None) -> list[dict]:
    q = (select(Task, DeliveryRole.name, TaskCategory.key, Module.name)
         .join(Module, Module.id == Task.module_id)
         .outerjoin(DeliveryRole, DeliveryRole.id == Task.delivery_role_id)
         .outerjoin(TaskCategory, TaskCategory.id == Task.category_id)
         .where(Task.estimate_id == estimate_id, Task.removed.is_(False), Task.enabled.is_(True),
                Module.removed.is_(False)))
    out = []
    f = 1 + percent / 100.0
    for t, rname, ckey, mname in db.execute(q):
        if role_name and (rname or "").lower() != role_name.lower():
            continue
        if category_key and ckey != category_key:
            continue
        if module_name and (mname or "").lower() != module_name.lower():
            continue
        out.append({"task_id": str(t.id), "title": t.title, "old_min": t.min_hours, "old_max": t.max_hours,
                    "new_min": max(0.25, round_half(t.min_hours * f)), "new_max": max(0.5, round_half(t.max_hours * f))})
    return out


def _resolve_module(db: Session, estimate_id: uuid.UUID, payload: dict, actor: es.Actor) -> uuid.UUID:
    if payload.get("module_id"):
        return uuid.UUID(payload["module_id"])
    name = payload.get("module_name") or "Additional scope"
    m = db.scalars(select(Module).where(Module.estimate_id == estimate_id, Module.name == name,
                                        Module.removed.is_(False))).first()
    return m.id if m else es.create_module(db, estimate_id, name, actor).id


def _apply(db: Session, estimate_id: uuid.UUID, op: dict, actor: es.Actor) -> None:
    _, cat2id = category_maps(db)
    _, role2id = role_maps(db)
    pl: dict[str, Any] = op["payload"]
    reason = op.get("rationale") or None
    if op["type"] == "add_module":
        es.create_module(db, estimate_id, pl["name"], actor, pl.get("description", ""))
    elif op["type"] == "add_task":
        mid_ = _resolve_module(db, estimate_id, pl, actor)
        es.create_task(db, estimate_id, {
            "module_id": mid_, "title": pl["title"], "description": pl.get("description", ""),
            "category_id": cat2id.get(pl.get("category_key", "other")), "delivery_role_id": role2id.get(pl.get("role_name", "")),
            "min_hours": pl["min_hours"], "max_hours": pl["max_hours"], "rationale": reason or "",
        }, actor, reason_tag=pl.get("reason_tag") or "scope_added", reason_text=reason)
    elif op["type"] == "update_task":
        ch = dict(pl.get("changes", {}))
        if "category_key" in ch:
            ch["category_id"] = cat2id.get(ch.pop("category_key"))
        if "role_name" in ch:
            ch["delivery_role_id"] = role2id.get(ch.pop("role_name"))
        es.update_task(db, uuid.UUID(pl["task_id"]), ch, actor, reason_tag=pl.get("reason_tag"), reason_text=reason)
    elif op["type"] == "remove_task":
        es.remove_task(db, uuid.UUID(pl["task_id"]), actor, reason_tag=pl.get("reason_tag") or "scope_removed",
                       reason_text=reason)
    elif op["type"] == "split_task":
        orig = es.get_task(db, uuid.UUID(pl["task_id"]))
        for part in pl["parts"]:
            es.create_task(db, estimate_id, {
                "module_id": orig.module_id, "title": part["title"], "description": part.get("description", ""),
                "category_id": orig.category_id, "delivery_role_id": orig.delivery_role_id,
                "min_hours": part["min_hours"], "max_hours": part["max_hours"],
            }, actor, reason_text=f"split from '{orig.title}'")
        es.remove_task(db, orig.id, actor, reason_text="split into subtasks")
    elif op["type"] == "bulk_adjust":
        for c in pl["changes"]:
            es.update_task(db, uuid.UUID(c["task_id"]), {"min_hours": c["new_min"], "max_hours": c["new_max"]}, actor,
                           reason_tag=pl.get("reason_tag"), reason_text=reason)
    elif op["type"] == "remove_module":
        es.remove_module(db, uuid.UUID(pl["module_id"]), actor)
    else:
        raise AppError("unknown_op", f"Unknown op type {op['type']}", 422)


def resolve_op(db: Session, proposal_id: uuid.UUID, op_id: str, accept: bool, user_id: uuid.UUID | None,
               reason: str | None = None) -> ChangeProposal:
    prop = get_proposal(db, proposal_id)
    es.ensure_draft(db, prop.estimate_id)
    ops = [dict(o) for o in prop.ops]
    op = next((o for o in ops if o["id"] == op_id), None)
    if op is None:
        raise NotFound("Operation")
    if op["status"] != "pending":
        raise Conflict(f"Operation already {op['status']}")
    if accept:
        # Agent-originated changes are logged with actor=agent and the proposal id; the accepting user is recorded.
        _apply(db, prop.estimate_id, op, es.Actor(op.get("actor", "agent"), user_id, prop.id))
        op["status"] = "accepted"
    else:
        es.log_event(db, prop.estimate_id, es.Actor("user", user_id, prop.id), "proposal_op_rejected",
                     field=op["type"], new={"op": op}, reason_text=reason)
        op["status"] = "rejected"
    op["resolved_at"] = datetime.now(UTC).isoformat()
    prop.ops = ops
    flag_modified(prop, "ops")
    statuses = {o["status"] for o in ops}
    if "pending" not in statuses:
        prop.status = "accepted" if statuses == {"accepted"} else "rejected" if statuses == {"rejected"} else "partial"
        prop.resolved_by = user_id
        prop.resolved_at = datetime.now(UTC)
    db.flush()
    return prop


def resolve_all(db: Session, proposal_id: uuid.UUID, accept: bool, user_id: uuid.UUID | None) -> ChangeProposal:
    prop = get_proposal(db, proposal_id)
    for op in list(prop.ops):
        if op["status"] == "pending":
            prop = resolve_op(db, proposal_id, op["id"], accept, user_id)
    return prop
