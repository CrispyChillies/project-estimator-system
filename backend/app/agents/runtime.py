"""Agent run loop. One run per session (lock), idempotent by key, cancellable, capped steps. Live/record mode
uses a LangChain tool-calling agent over the typed toolkit; fake/replay and slash commands use the
deterministic planner. Both emit the same SSE contract (docs/AGENT_PROTOCOL.md)."""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.agents import memory, planner
from app.agents.toolkit import TOOL_SPECS, RunContext, Toolkit, tool_result_text
from app.core.config import get_settings
from app.core.errors import Conflict
from app.db.models import AgentMessage, AgentSession
from app.db.session import SessionLocal
from app.llm.gateway import _usage, get_gateway

log = logging.getLogger(__name__)


def sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def acquire_lock(db: Session, session_id: uuid.UUID) -> None:
    stale = datetime.now(UTC) - timedelta(seconds=get_settings().agent_run_lock_stale_s)
    res = db.execute(update(AgentSession).where(
        AgentSession.id == session_id,
        or_(AgentSession.run_state != "running", AgentSession.last_activity_at.is_(None),
            AgentSession.last_activity_at < stale))
        .values(run_state="running", last_activity_at=datetime.now(UTC)))
    db.commit()
    if res.rowcount == 0:
        raise Conflict("A run is already in progress for this session")


def check_user_can_run(db: Session, user_id: uuid.UUID | None) -> None:
    from app.core.usage import check_concurrency

    check_concurrency(db, user_id)


def _set_state(session_id: uuid.UUID, state: str) -> None:
    with SessionLocal() as db:
        db.execute(update(AgentSession).where(AgentSession.id == session_id)
                   .values(run_state=state, last_activity_at=datetime.now(UTC)))
        db.commit()


def cancelled(session_id: uuid.UUID) -> bool:
    with SessionLocal() as db:
        return db.scalar(select(AgentSession.run_state).where(AgentSession.id == session_id)) == "cancelling"


class RunUsage(BaseCallbackHandler):
    def __init__(self) -> None:
        self.tin = self.tout = 0
        self.cost = 0.0

    def on_llm_end(self, response, **kwargs):  # noqa: ANN001
        msg = response.generations[0][0].message if response.generations and response.generations[0] else None
        tin, tout, cached, _ = _usage(msg)
        self.tin += tin
        self.tout += tout
        self.cost += get_gateway().cost(tin, tout, cached)


def _lc_tools(kit: Toolkit) -> list:
    from langchain_core.tools import StructuredTool

    def make(name: str, schema, desc: str):
        def fn(**kw: Any) -> str:
            return tool_result_text(kit.call(name, kw))
        return StructuredTool.from_function(func=fn, name=name, description=desc, args_schema=schema)

    return [make(n, s, d) for n, (s, d, _w) in TOOL_SPECS.items()]


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "".join(c.get("text", "") for c in content if isinstance(c, dict))


HEARTBEAT_S = 15.0
_DONE = object()


def stream_run(session_id: uuid.UUID, text: str, user_id: uuid.UUID | None, idempotency_key: str | None = None,
               *, model=None, selection: list[str] | None = None, heartbeat_s: float = HEARTBEAT_S) -> Iterator[str]:
    """SSE stream for one run. The run executes in a worker thread so a heartbeat can be sent while the model is
    thinking, and so a client disconnect never aborts it: everything is persisted, the client resumes from the DB.
    Caller must hold the session lock (acquire_lock); it is always released."""
    import contextvars
    import queue
    import threading

    q: queue.Queue = queue.Queue()

    def work() -> None:
        try:
            for item in _guarded(session_id, text, user_id, idempotency_key, model, selection):
                q.put(item)
        finally:
            q.put(_DONE)

    ctx = contextvars.copy_context()
    threading.Thread(target=ctx.run, args=(work,), daemon=True, name=f"agent-run-{session_id}").start()
    while True:
        try:
            item = q.get(timeout=heartbeat_s)
        except queue.Empty:
            yield sse("heartbeat", {"ts": datetime.now(UTC).isoformat()})
            continue
        if item is _DONE:
            return
        yield item


def run_in_background(session_id: uuid.UUID, text: str, user_id: uuid.UUID | None,
                      idempotency_key: str | None = None, selection: list[str] | None = None) -> None:
    """Polling transport: same run, no stream; the client polls messages/operations until run_state is idle."""
    import contextvars
    import threading

    ctx = contextvars.copy_context()

    def work() -> None:
        for _ in _guarded(session_id, text, user_id, idempotency_key, None, selection):
            pass

    threading.Thread(target=ctx.run, args=(work,), daemon=True, name=f"agent-bg-{session_id}").start()


def _guarded(session_id: uuid.UUID, text: str, user_id, key, model, selection) -> Iterator[str]:
    from app.core.usage import use_llm_user

    try:
        with SessionLocal() as db, use_llm_user(user_id):
            yield from _run(db, session_id, text, user_id, key, model, selection or [])
    except Exception as e:  # never leave the stream without a terminal event
        log.exception("agent run failed")
        yield sse("error", {"code": getattr(e, "code", "agent_error"),
                            "message": getattr(e, "message", None) or type(e).__name__})
        yield sse("run_done", {"status": "failed"})
    finally:
        _set_state(session_id, "idle")


def _run(db: Session, session_id: uuid.UUID, text: str, user_id, key, model, selection: list[str]) -> Iterator[str]:
    s = db.get(AgentSession, session_id)
    if key:
        prev = db.scalar(select(AgentMessage).where(AgentMessage.session_id == s.id,
                                                    AgentMessage.idempotency_key == key))
        if prev is not None:
            reply = db.scalar(select(AgentMessage).where(AgentMessage.session_id == s.id, AgentMessage.role == "assistant",
                                                         AgentMessage.created_at > prev.created_at)
                              .order_by(AgentMessage.created_at))
            yield sse("run_started", {"session_id": str(s.id), "duplicate": True})
            if reply:
                yield sse("message_done", {"message_id": str(reply.id), "text": reply.content})
            yield sse("run_done", {"status": "duplicate", "batch_id": str(reply.batch_id) if reply else None})
            return
    batch_id = uuid.uuid4()
    umsg = AgentMessage(id=uuid.uuid4(), session_id=s.id, role="user", content=text, idempotency_key=key,
                        batch_id=batch_id, payload={"selection": selection} if selection else {})
    db.add(umsg)
    s.last_activity_at = datetime.now(UTC)
    if s.title in ("New session", "") and not text.startswith("/"):
        s.title = text[:60]
    if s.use_memory:
        memory.roll_summary(db, s)
    db.commit()
    yield sse("run_started", {"run_id": str(batch_id), "session_id": str(s.id), "batch_id": str(batch_id),
                              "message_id": str(umsg.id), "apply_mode": s.apply_mode})

    ctx = RunContext(db, s, user_id, batch_id, umsg.id)
    ctx.selection = [t for t in selection if _task_in_estimate(db, t, s.estimate_id)]
    kit = Toolkit(ctx)
    gw = get_gateway()
    offline = model is None and (gw.mode in ("fake", "replay") or text.startswith("/"))
    usage = RunUsage()
    reply = ""
    status = "completed"

    def flush() -> Iterator[str]:
        db.commit()
        for ev, data in ctx.drain():
            yield sse(ev, data)

    if offline:
        yield sse("stage", {"label": "Planning (offline)"})
        gen = planner.plan(kit, text)
        try:
            while True:
                next(gen)
                yield from flush()
                if cancelled(s.id):
                    status = "cancelled"
                    break
        except StopIteration as stop:
            reply = stop.value or ""
        yield from flush()
        for w in re.split(r"(\s+)", reply):
            if w:
                yield sse("message_delta", {"text": w})
    else:
        from langchain.agents import create_agent
        from langchain_core.messages import AIMessage, ToolMessage

        yield sse("stage", {"label": "Thinking"})
        agent = create_agent(model or gw.chat_model(), tools=_lc_tools(kit), system_prompt=memory.system_prompt(db, s))
        note = ""
        if ctx.selection:
            from app.db.models import Task

            titles = [f"{t.id} ({t.title})" for t in db.scalars(select(Task).where(Task.id.in_(
                [uuid.UUID(x) for x in ctx.selection])))]
            note = "\n\n[The user selected these rows; 'these'/'selected' refers to them: " + "; ".join(titles) + "]"
        msgs = memory.history_messages(db, s) + [{"role": "user", "content": text + note}]
        steps = get_settings().agent_max_steps
        last_id = None
        try:
            for chunk, _meta in agent.stream({"messages": msgs}, stream_mode="messages",
                                             config={"callbacks": [usage], "recursion_limit": 2 * steps + 1}):
                if isinstance(chunk, AIMessage):
                    content = _text(chunk.content)
                    if content:
                        if last_id is not None and chunk.id != last_id and reply:
                            content = "\n\n" + content
                        last_id = chunk.id
                        reply += content
                        yield sse("message_delta", {"text": content})
                elif isinstance(chunk, ToolMessage):
                    yield from flush()
                    if cancelled(s.id):
                        status = "cancelled"
                        break
                    if ctx.paused and reply:
                        break
        except Exception as e:
            if type(e).__name__ != "GraphRecursionError":
                raise
            note = f"\n\n(Stopped after {steps} steps.)"
            reply += note
            yield sse("message_delta", {"text": note})
        yield from flush()
        if not reply:
            reply = "Waiting for your confirmation." if ctx.paused else "Done."
            yield sse("message_delta", {"text": reply})

    if ctx.applied:
        from app.services.summary import compute_summary

        compute_summary(db, s.estimate_id)
    amsg = AgentMessage(id=uuid.uuid4(), session_id=s.id, role="assistant", content=reply, tool_calls=ctx.tool_log,
                        batch_id=batch_id, input_tokens=usage.tin, output_tokens=usage.tout,
                        payload={"status": ctx.paused or status, "ask": ctx.ask, "references": ctx.references})
    db.add(amsg)
    s.cost_usd = (s.cost_usd or 0) + usage.cost
    s.tokens = (s.tokens or 0) + usage.tin + usage.tout
    s.model_key = gw.model_key
    s.last_activity_at = datetime.now(UTC)
    db.commit()
    yield sse("message_done", {"message_id": str(amsg.id), "text": reply})
    yield sse("cost_update", {"tokens": usage.tin + usage.tout, "cost_usd": round(usage.cost, 5),
                              "session_cost_usd": round(s.cost_usd, 5), "offline": offline})
    yield sse("run_done", {"status": ctx.paused or status, "batch_id": str(batch_id), "applied": len(ctx.applied)})


def _task_in_estimate(db: Session, task_id: str, estimate_id: uuid.UUID) -> bool:
    from app.db.models import Task

    try:
        t = db.get(Task, uuid.UUID(task_id))
    except ValueError:
        return False
    return bool(t and t.estimate_id == estimate_id and not t.removed)
