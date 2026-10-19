"""OperationExecutor: the agent's only way to change an estimate.

Every agent write is a primitive op recorded in `agent_operations` with its inverse, and routed through
`services.estimates` (so `edit_events` are written with operation/batch/session ids). Undo applies the stored
inverse ops as new events - log rows are never edited. Undo skips tasks the user changed after the op (partial).

Primitive ops (dicts with an "op" key):
  create_module{name}            rename_module{module_id,name}      remove_module{module_id}
  restore_module{module_id}      create_task{module_id,title,min_hours,max_hours,...}
  update_task{task_id,changes,expected_version?}     remove_task{task_id}     restore_task{task_id}
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import AgentOperation, Module, Task
from app.services import estimates as es

_UPDATABLE = ("title", "description", "category_id", "delivery_role_id", "min_hours", "max_hours", "enabled",
              "module_id", "position", "confidence", "rationale")


def _s(v: Any) -> Any:
    return str(v) if isinstance(v, uuid.UUID) else v


def _uuid(v: Any) -> uuid.UUID | None:
    return v if v is None or isinstance(v, uuid.UUID) else uuid.UUID(str(v))


def included_total(db: Session, estimate_id: uuid.UUID) -> tuple[float, float]:
    removed_mods = set(db.scalars(select(Module.id).where(Module.estimate_id == estimate_id, Module.removed)))
    lo = hi = 0.0
    for t in db.scalars(select(Task).where(Task.estimate_id == estimate_id)):
        if es.is_effectively_included(t, t.module_id in removed_mods):
            lo += t.min_hours
            hi += t.max_hours
    return round(lo, 2), round(hi, 2)


@dataclass
class OpResult:
    op: dict
    inverse: list[dict]
    touched_task_ids: list[str] = field(default_factory=list)
    touched_module_ids: list[str] = field(default_factory=list)
    created_id: str | None = None


class OperationExecutor:
    def __init__(self, db: Session, estimate_id: uuid.UUID, *, user_id: uuid.UUID | None = None,
                 session_id: uuid.UUID | None = None):
        self.db = db
        self.estimate_id = estimate_id
        self.user_id = user_id
        self.session_id = session_id

    def _actor(self, operation_id: uuid.UUID | None, batch_id: uuid.UUID | None) -> es.Actor:
        return es.Actor("agent", self.user_id, operation_id=operation_id, batch_id=batch_id, session_id=self.session_id)

    # ---- primitive application ----
    def _apply_one(self, op: dict, actor: es.Actor) -> OpResult:
        db, kind = self.db, op["op"]
        if kind == "create_module":
            m = es.create_module(db, self.estimate_id, op["name"], actor, op.get("description", ""))
            return OpResult(op, [{"op": "remove_module", "module_id": str(m.id)}],
                            touched_module_ids=[str(m.id)], created_id=str(m.id))
        if kind in ("rename_module", "remove_module", "restore_module"):
            m = self._module(op["module_id"])
            if kind == "rename_module":
                inv = [{"op": "rename_module", "module_id": str(m.id), "name": m.name}]
                es.rename_module(db, m.id, op["name"], actor)
                return OpResult(op, inv, touched_module_ids=[str(m.id)])
            if kind == "remove_module":
                was_removed = m.removed
                live = [t.id for t in db.scalars(select(Task).where(Task.module_id == m.id, Task.removed.is_(False)))]
                inv = [{"op": "restore_module", "module_id": str(m.id)}] + [
                    {"op": "restore_task", "task_id": str(t)} for t in live]
                es.remove_module(db, m.id, actor)
                return OpResult(op, [] if was_removed else inv, [str(t) for t in live], [str(m.id)])
            es.restore_module(db, m.id, actor)
            return OpResult(op, [{"op": "remove_module", "module_id": str(m.id)}], touched_module_ids=[str(m.id)])
        if kind == "create_task":
            data = {k: v for k, v in op.items() if k != "op"}
            data["module_id"] = _uuid(data["module_id"])
            for k in ("category_id", "delivery_role_id"):
                data[k] = _uuid(data.get(k))
            t = es.create_task(db, self.estimate_id, data, actor, origin="agent")
            return OpResult(op, [{"op": "remove_task", "task_id": str(t.id)}], [str(t.id)], created_id=str(t.id))
        t = self._task(op["task_id"])
        if kind == "update_task":
            changes = {k: v for k, v in op.get("changes", {}).items() if k in _UPDATABLE}
            for k in ("category_id", "delivery_role_id", "module_id"):
                if k in changes:
                    changes[k] = _uuid(changes[k])
            old = {k: _s(getattr(t, k)) for k in changes}
            es.update_task(db, t.id, changes, actor, reason_tag=op.get("reason_tag"), reason_text=op.get("reason"),
                           expected_version=op.get("expected_version"))
            return OpResult(op, [{"op": "update_task", "task_id": str(t.id), "changes": old}], [str(t.id)])
        if kind == "remove_task":
            was = t.removed
            es.remove_task(db, t.id, actor, reason_text=op.get("reason"))
            return OpResult(op, [] if was else [{"op": "restore_task", "task_id": str(t.id)}], [str(t.id)])
        if kind == "restore_task":
            was = t.removed
            es.restore_task(db, t.id, actor)
            return OpResult(op, [{"op": "remove_task", "task_id": str(t.id)}] if was else [], [str(t.id)])
        raise AppError("unknown_op", f"Unknown operation '{kind}'", 422)

    def _task(self, tid: Any) -> Task:
        t = self.db.get(Task, _uuid(tid))
        if t is None or t.estimate_id != self.estimate_id:
            raise AppError("task_not_found", f"Task {tid} does not exist in this estimate", 404)
        return t

    def _module(self, mid: Any) -> Module:
        m = self.db.get(Module, _uuid(mid))
        if m is None or m.estimate_id != self.estimate_id:
            raise AppError("module_not_found", f"Group {mid} does not exist in this estimate", 404)
        return m

    # ---- public API ----
    def preview(self, ops: list[dict]) -> dict:
        """Dry-run inside a SAVEPOINT; nothing persists."""
        before = included_total(self.db, self.estimate_id)
        sp = self.db.begin_nested()
        try:
            results = [self._apply_one(op, self._actor(None, None)) for op in ops]
            self.db.flush()
            after = included_total(self.db, self.estimate_id)
        finally:
            sp.rollback()
        self.db.expire_all()
        return {"before": before, "after": after,
                "touched_task_ids": sorted({x for r in results for x in r.touched_task_ids}),
                "deletes": sum(1 for o in ops if o["op"] in ("remove_task", "remove_module"))}

    def record(self, op_type: str, args: dict, ops: list[dict], *, batch_id: uuid.UUID, summary: str = "",
               status: str = "pending", tool_call_id: str | None = None,
               message_id: uuid.UUID | None = None) -> AgentOperation:
        rec = AgentOperation(id=uuid.uuid4(), session_id=self.session_id, estimate_id=self.estimate_id,
                             batch_id=batch_id, op_type=op_type, args={**args, "_ops": ops}, status=status,
                             summary=summary, tool_call_id=tool_call_id, message_id=message_id)
        self.db.add(rec)
        self.db.flush()
        return rec

    def apply(self, rec: AgentOperation) -> AgentOperation:
        """Apply all primitive ops of one operation atomically (SAVEPOINT); failure marks it failed."""
        es.ensure_draft(self.db, self.estimate_id)
        actor = self._actor(rec.id, rec.batch_id)
        before = included_total(self.db, self.estimate_id)
        sp = self.db.begin_nested()
        try:
            results = [self._apply_one(op, actor) for op in rec.args.get("_ops", [])]
            self.db.flush()
            sp.commit()
        except AppError as e:
            sp.rollback()
            rec.status, rec.result = "failed", {"error": e.code, "message": e.message}
            self.db.flush()
            return rec
        inverse: list[dict] = []
        for r in reversed(results):
            inverse.extend(r.inverse)
        versions = {tid: self.db.get(Task, uuid.UUID(tid)).row_version
                    for r in results for tid in r.touched_task_ids}
        rec.inverse_ops = inverse
        rec.status, rec.applied_at = "applied", datetime.now(UTC)
        rec.result = {"before": before, "after": included_total(self.db, self.estimate_id),
                      "touched_task_ids": sorted(versions), "versions_after": versions,
                      "created_ids": [r.created_id for r in results if r.created_id]}
        self.db.flush()
        return rec

    def undo(self, rec: AgentOperation) -> dict:
        """Apply stored inverse ops. Tasks the user changed since the op are skipped (partial undo)."""
        if rec.status != "applied":
            raise AppError("not_applied", f"Operation is {rec.status}; only applied operations can be undone", 409)
        es.ensure_draft(self.db, self.estimate_id)
        versions = rec.result.get("versions_after", {})
        actor = self._actor(rec.id, rec.batch_id)
        applied, skipped = 0, []
        for inv in rec.inverse_ops:
            tid = inv.get("task_id")
            if tid and tid in versions:
                t = self.db.get(Task, uuid.UUID(tid))
                if t is not None and t.row_version != versions[tid]:
                    skipped.append({"task_id": tid, "title": t.title, "reason": "edited after the agent change"})
                    continue
            self._apply_one(inv, actor)
            self.db.flush()
            applied += 1
            if tid and tid in versions:  # our own bump must not look like a user edit to later inverses
                versions[tid] = self.db.get(Task, uuid.UUID(tid)).row_version
        rec.status, rec.reverted_at = "reverted", datetime.now(UTC)
        rec.result = {**rec.result, "undo": {"applied": applied, "skipped": skipped}}
        self.db.flush()
        return {"operation_id": str(rec.id), "applied": applied, "skipped": skipped, "partial": bool(skipped)}

    def undo_batch(self, batch_id: uuid.UUID) -> list[dict]:
        recs = list(self.db.scalars(select(AgentOperation).where(
            AgentOperation.batch_id == batch_id, AgentOperation.status == "applied")
            .order_by(AgentOperation.applied_at.desc())))
        return [self.undo(r) for r in recs]
