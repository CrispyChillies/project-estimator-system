"""Agent Panel API: sessions, runs (SSE), cancel, confirm/reject/undo operations, project memories."""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.runtime import acquire_lock, check_user_can_run, stream_run
from app.api.deps import current_user_id
from app.core.errors import AppError, NotFound
from app.core.usage import AIRateLimit
from app.db.models import AgentMessage, AgentOperation, AgentSession, ProjectMemory
from app.db.session import get_db
from app.services import estimates as es
from app.services.operations import OperationExecutor
from app.services.summary import compute_summary

router = APIRouter(tags=["agent-panel"])


class SessionIn(BaseModel):
    title: str | None = Field(None, max_length=200)
    apply_mode: Literal["auto", "review"] = "auto"


class SessionPatch(BaseModel):
    title: str | None = Field(None, max_length=200)
    pinned: bool | None = None
    apply_mode: Literal["auto", "review"] | None = None
    use_memory: bool | None = None
    state: dict[str, Any] | None = None
    status: Literal["active", "archived"] | None = None


class RunIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    idempotency_key: str | None = Field(None, max_length=80)


class MemoryIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    kind: Literal["fact", "decision", "constraint", "preference"] = "fact"


class MemoryPatch(BaseModel):
    text: str | None = Field(None, min_length=1, max_length=1000)
    enabled: bool | None = None


def _session_out(s: AgentSession) -> dict:
    return {"id": str(s.id), "estimate_id": str(s.estimate_id), "title": s.title, "summary": s.summary,
            "state": s.state or {}, "status": s.status, "pinned": s.pinned, "apply_mode": s.apply_mode,
            "use_memory": s.use_memory, "run_state": s.run_state, "cost_usd": s.cost_usd, "tokens": s.tokens,
            "model_key": s.model_key, "created_at": s.created_at, "last_activity_at": s.last_activity_at}


def _op_out(r: AgentOperation) -> dict:
    return {"id": str(r.id), "session_id": str(r.session_id) if r.session_id else None, "batch_id": str(r.batch_id),
            "op_type": r.op_type, "status": r.status, "summary": r.summary, "result": r.result,
            "tool_call_id": r.tool_call_id, "message_id": str(r.message_id) if r.message_id else None,
            "created_at": r.created_at, "applied_at": r.applied_at, "reverted_at": r.reverted_at}


def _msg_out(m: AgentMessage) -> dict:
    return {"id": str(m.id), "role": m.role, "content": m.content, "tool_calls": m.tool_calls or [],
            "payload": m.payload or {}, "batch_id": str(m.batch_id) if m.batch_id else None, "created_at": m.created_at}


def _session(db: Session, sid: uuid.UUID) -> AgentSession:
    s = db.get(AgentSession, sid)
    if s is None or s.status == "deleted":
        raise NotFound("Session")
    return s


def _event(db: Session, s: AgentSession, text: str, payload: dict) -> None:
    db.add(AgentMessage(session_id=s.id, role="system_event", content=text, payload=payload))
    s.last_activity_at = datetime.now(UTC)


# ---------- sessions ----------
@router.get("/estimates/{estimate_id}/agent/sessions")
def list_sessions(estimate_id: uuid.UUID, db: Session = Depends(get_db)) -> list[dict]:
    q = (select(AgentSession).where(AgentSession.estimate_id == estimate_id, AgentSession.status != "deleted",
                                    AgentSession.mode == "chat")
         .order_by(AgentSession.pinned.desc(), AgentSession.last_activity_at.desc().nulls_last(),
                   AgentSession.created_at.desc()))
    return [_session_out(s) for s in db.scalars(q)]


@router.post("/estimates/{estimate_id}/agent/sessions", status_code=201)
def create_session(estimate_id: uuid.UUID, body: SessionIn, db: Session = Depends(get_db),
                   uid=Depends(current_user_id)) -> dict:
    es.get_estimate(db, estimate_id)
    s = AgentSession(estimate_id=estimate_id, mode="chat", created_by=uid, title=body.title or "New session",
                     apply_mode=body.apply_mode, state={}, last_activity_at=datetime.now(UTC))
    db.add(s)
    db.commit()
    return _session_out(s)


@router.patch("/agent/sessions/{session_id}")
def patch_session(session_id: uuid.UUID, body: SessionPatch, db: Session = Depends(get_db)) -> dict:
    s = _session(db, session_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    db.commit()
    return _session_out(s)


@router.delete("/agent/sessions/{session_id}", status_code=204)
def delete_session(session_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    _session(db, session_id).status = "deleted"
    db.commit()
    return Response(status_code=204)


@router.get("/agent/sessions/{session_id}/messages")
def session_messages(session_id: uuid.UUID, db: Session = Depends(get_db)) -> list[dict]:
    _session(db, session_id)
    return [_msg_out(m) for m in db.scalars(select(AgentMessage).where(AgentMessage.session_id == session_id)
                                            .order_by(AgentMessage.created_at))]


@router.get("/agent/sessions/{session_id}/operations")
def session_operations(session_id: uuid.UUID, db: Session = Depends(get_db)) -> list[dict]:
    _session(db, session_id)
    return [_op_out(r) for r in db.scalars(select(AgentOperation).where(AgentOperation.session_id == session_id)
                                           .order_by(AgentOperation.created_at))]


# ---------- runs ----------
@router.post("/agent/sessions/{session_id}/runs", dependencies=[AIRateLimit])
def start_run(session_id: uuid.UUID, body: RunIn, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    """SSE stream; 409 if a run is already active for this session. Contract: docs/AGENT_PROTOCOL.md."""
    s = _session(db, session_id)
    es.ensure_draft(db, s.estimate_id)
    check_user_can_run(db, uid)
    acquire_lock(db, s.id)
    return StreamingResponse(stream_run(s.id, body.text, uid, body.idempotency_key), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/agent/sessions/{session_id}/cancel", status_code=202)
def cancel_run(session_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    s = _session(db, session_id)
    if s.run_state == "running":
        s.run_state = "cancelling"
        db.commit()
    return {"run_state": s.run_state}


# ---------- operations ----------
def _op(db: Session, op_id: uuid.UUID) -> AgentOperation:
    r = db.get(AgentOperation, op_id)
    if r is None:
        raise NotFound("Operation")
    return r


def _finish(db: Session, r: AgentOperation, extra: dict | None = None) -> dict:
    compute_summary(db, r.estimate_id)
    db.commit()
    return {**_op_out(r), **(extra or {})}


@router.post("/agent/operations/{op_id}/confirm")
def confirm_op(op_id: uuid.UUID, db: Session = Depends(get_db), uid=Depends(current_user_id)) -> dict:
    r = _op(db, op_id)
    if r.status != "awaiting_confirmation":
        raise AppError("not_awaiting", f"Operation is {r.status}", 409)
    ex = OperationExecutor(db, r.estimate_id, user_id=uid, session_id=r.session_id)
    ex.apply(r)
    s = db.get(AgentSession, r.session_id) if r.session_id else None
    if s:
        _event(db, s, f"User confirmed: {r.summary}" + (" (failed)" if r.status == "failed" else ""),
               {"operation_id": str(r.id), "status": r.status})
    return _finish(db, r)


@router.post("/agent/operations/{op_id}/reject")
def reject_op(op_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    r = _op(db, op_id)
    if r.status != "awaiting_confirmation":
        raise AppError("not_awaiting", f"Operation is {r.status}", 409)
    r.status = "rejected"
    s = db.get(AgentSession, r.session_id) if r.session_id else None
    if s:
        _event(db, s, f"User rejected: {r.summary}", {"operation_id": str(r.id), "status": "rejected"})
    db.commit()
    return _op_out(r)


@router.post("/agent/operations/{op_id}/undo")
def undo_op(op_id: uuid.UUID, db: Session = Depends(get_db), uid=Depends(current_user_id)) -> dict:
    r = _op(db, op_id)
    res = OperationExecutor(db, r.estimate_id, user_id=uid, session_id=r.session_id).undo(r)
    s = db.get(AgentSession, r.session_id) if r.session_id else None
    if s:
        _event(db, s, f"User undid: {r.summary}" + (" (partial)" if res["partial"] else ""), res)
    return _finish(db, r, {"undo": res})


@router.post("/agent/batches/{batch_id}/undo")
def undo_batch(batch_id: uuid.UUID, db: Session = Depends(get_db), uid=Depends(current_user_id)) -> dict:
    first = db.scalar(select(AgentOperation).where(AgentOperation.batch_id == batch_id))
    if first is None:
        raise NotFound("Batch")
    res = OperationExecutor(db, first.estimate_id, user_id=uid, session_id=first.session_id).undo_batch(batch_id)
    s = db.get(AgentSession, first.session_id) if first.session_id else None
    if s and res:
        _event(db, s, f"User undid {len(res)} change(s) from one turn", {"batch_id": str(batch_id), "results": res})
    compute_summary(db, first.estimate_id)
    db.commit()
    return {"batch_id": str(batch_id), "results": res}


# ---------- project memories ----------
def _mem_out(m: ProjectMemory) -> dict:
    return {"id": str(m.id), "kind": m.kind, "text": m.text, "origin": m.origin, "enabled": m.enabled,
            "created_at": m.created_at}


@router.get("/estimates/{estimate_id}/memories")
def list_memories(estimate_id: uuid.UUID, db: Session = Depends(get_db)) -> list[dict]:
    pid = es.get_estimate(db, estimate_id).project_id
    return [_mem_out(m) for m in db.scalars(select(ProjectMemory).where(ProjectMemory.project_id == pid)
                                            .order_by(ProjectMemory.created_at))]


@router.post("/estimates/{estimate_id}/memories", status_code=201)
def add_memory(estimate_id: uuid.UUID, body: MemoryIn, db: Session = Depends(get_db)) -> dict:
    est = es.get_estimate(db, estimate_id)
    m = ProjectMemory(project_id=est.project_id, kind=body.kind, text=body.text, origin="user")
    db.add(m)
    db.commit()
    return _mem_out(m)


@router.patch("/memories/{memory_id}")
def patch_memory(memory_id: uuid.UUID, body: MemoryPatch, db: Session = Depends(get_db)) -> dict:
    m = db.get(ProjectMemory, memory_id)
    if m is None:
        raise NotFound("Memory")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(m, k, v)
    db.commit()
    return _mem_out(m)


@router.delete("/memories/{memory_id}", status_code=204)
def delete_memory(memory_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    m = db.get(ProjectMemory, memory_id)
    if m is None:
        raise NotFound("Memory")
    db.delete(m)
    db.commit()
    return Response(status_code=204)
