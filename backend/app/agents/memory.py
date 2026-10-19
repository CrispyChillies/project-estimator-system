"""Session memory: rolling summary of old turns once history exceeds AGENT_HISTORY_TOKEN_BUDGET, plus the
context block (binding session state, project memories, estimate overview) for the live model."""

from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AgentMessage, AgentSession, Estimate, Module, ProjectMemory, Task
from app.prompts import render
from app.services.learning import active_rules
from app.services.reference import role_maps

SUMMARY_CHAR_CAP = 6000


def tokens(s: str) -> int:
    return math.ceil(len(s or "") / 4)


def _after_summary(db: Session, s: AgentSession) -> list[AgentMessage]:
    q = select(AgentMessage).where(AgentMessage.session_id == s.id).order_by(AgentMessage.created_at)
    if s.summary_upto_message_id:
        cut = db.get(AgentMessage, s.summary_upto_message_id)
        if cut is not None:
            q = q.where(AgentMessage.created_at > cut.created_at)
    return list(db.scalars(q))


def _line(m: AgentMessage) -> str:
    if m.role == "user":
        return f"User: {m.content[:240]}"
    if m.role == "assistant":
        tools = ", ".join(sorted({c.get("name", "") for c in m.tool_calls or []}))
        return f"Agent: {m.content[:240]}" + (f" [tools: {tools}]" if tools else "")
    return f"Event: {m.content[:160]}"


def roll_summary(db: Session, s: AgentSession) -> bool:
    """Fold the oldest turns into `summary` until the remaining history fits half the budget. Deterministic
    (extractive) so it costs nothing and is reproducible."""
    budget = get_settings().agent_history_token_budget
    msgs = _after_summary(db, s)
    total = sum(tokens(m.content) for m in msgs)
    if total <= budget:
        return False
    folded: list[AgentMessage] = []
    while msgs and total > budget // 2:
        m = msgs.pop(0)
        total -= tokens(m.content)
        folded.append(m)
    lines = "\n".join(_line(m) for m in folded)
    s.summary = ((s.summary + "\n" if s.summary else "") + lines)[-SUMMARY_CHAR_CAP:]
    s.summary_upto_message_id = folded[-1].id
    db.flush()
    return True


def history_messages(db: Session, s: AgentSession, exclude_last: bool = True) -> list[dict]:
    msgs = _after_summary(db, s)
    if exclude_last and msgs and msgs[-1].role == "user":
        msgs = msgs[:-1]
    out = []
    for m in msgs:
        if m.role in ("user", "assistant") and m.content:
            out.append({"role": m.role, "content": m.content})
        elif m.role == "system_event":
            out.append({"role": "user", "content": f"[event] {m.content}"})
    return out


def estimate_overview(db: Session, estimate_id, max_tasks: int = 80) -> str:
    id2r, _ = role_maps(db)
    mods = {m.id: m for m in db.scalars(select(Module).where(Module.estimate_id == estimate_id))}
    tasks = list(db.scalars(select(Task).where(Task.estimate_id == estimate_id, Task.removed.is_(False))
                            .order_by(Task.module_id, Task.position)))
    tasks = [t for t in tasks if not mods[t.module_id].removed]
    lo = sum(t.min_hours for t in tasks if t.enabled)
    hi = sum(t.max_hours for t in tasks if t.enabled)
    lines = [f"{len(tasks)} tasks, visible total {lo:g}–{hi:g} h. Groups: "
             + "; ".join(m.name for m in sorted(mods.values(), key=lambda m: m.position) if not m.removed)]
    if len(tasks) <= max_tasks:
        lines += [f"{t.id} | {mods[t.module_id].name} | {id2r.get(t.delivery_role_id, '-')} | {t.title} | "
                  f"{t.min_hours:g}-{t.max_hours:g} h" + ("" if t.enabled else " (hidden)") for t in tasks]
    else:
        lines.append("(large estimate: call list_tasks for ids)")
    return "\n".join(lines)


def system_prompt(db: Session, s: AgentSession) -> str:
    pid = db.get(Estimate, s.estimate_id).project_id
    mems = list(db.scalars(select(ProjectMemory).where(ProjectMemory.project_id == pid, ProjectMemory.enabled)))
    use = s.use_memory
    mem_txt = "\n".join(f"- [{m.kind}, origin={m.origin}] {m.text}" for m in mems) if use and mems else "none"
    state = "\n".join(f"- {k}: {v}" for k, v in (s.state or {}).items()) or "none"
    return render("agent_panel", state=state, summary=(s.summary if use else "") or "none", memories=mem_txt,
                  rules="\n".join(f"- {r.text}" for r in active_rules(db)) or "none",
                  estimate=estimate_overview(db, s.estimate_id))
