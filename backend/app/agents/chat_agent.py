"""Chat agent: LangChain tool-calling agent (live) or deterministic command parser (fake/replay).
Tools are read-only or proposal-creating; they NEVER mutate the estimate."""

from __future__ import annotations

import functools
import json
import logging
import math
import re
import uuid
from collections.abc import Iterator

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import templates as T
from app.db.models import (
    AgentMessage,
    AgentSession,
    DeliveryRole,
    Module,
    Task,
    TaskAIBaseline,
    TaskCategory,
)
from app.llm.gateway import get_gateway
from app.prompts import render
from app.services import proposals as pr
from app.services.learning import active_rules, load_stats
from app.services.retrieval import find_analogs

log = logging.getLogger(__name__)


def sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


class SplitPart(BaseModel):
    title: str
    min_hours: float
    max_hours: float


class AgentTools:
    def __init__(self, db: Session, estimate_id: uuid.UUID, session_id: uuid.UUID):
        self.db, self.estimate_id, self.session_id = db, estimate_id, session_id
        self.proposal = None
        self.touched = False

    def _proposal(self):
        if self.proposal is None:
            self.proposal = pr.new_proposal(self.db, self.estimate_id, self.session_id, "Agent proposal")
        self.touched = True
        return self.proposal

    def _rows(self):
        q = (select(Task, Module.name, DeliveryRole.name, TaskCategory.key)
             .join(Module, Module.id == Task.module_id)
             .outerjoin(DeliveryRole, DeliveryRole.id == Task.delivery_role_id)
             .outerjoin(TaskCategory, TaskCategory.id == Task.category_id)
             .where(Task.estimate_id == self.estimate_id, Task.removed.is_(False), Module.removed.is_(False))
             .order_by(Module.position, Task.position))
        return list(self.db.execute(q))

    def _find(self, ref: str) -> Task | None:
        try:
            t = self.db.get(Task, uuid.UUID(ref))
            if t and t.estimate_id == self.estimate_id:
                return t
        except ValueError:
            pass
        words = set(T.tokens(ref))
        best, score = None, 0
        for t, *_ in self._rows():
            s = len(words & set(T.tokens(t.title)))
            if s > score:
                best, score = t, s
        return best

    # ----- read-only -----
    def list_tasks(self) -> str:
        """List all tasks of the current estimate with id, module, role, category and hours."""
        return "\n".join(f"{t.id} | {m} | {r or '-'} | {c or '-'} | {t.title} | {t.min_hours}-{t.max_hours} h"
                         + ("" if t.enabled else " (disabled)") for t, m, r, c in self._rows())

    def get_task_details(self, task_ref: str) -> str:
        """Get details of a task by id or title."""
        t = self._find(task_ref)
        if not t:
            return "Task not found."
        return json.dumps({"id": str(t.id), "title": t.title, "description": t.description, "min_hours": t.min_hours,
                           "max_hours": t.max_hours, "rationale": t.rationale, "origin": t.origin})

    def explain_task(self, task_ref: str) -> str:
        """Explain why a task has its number: raw LLM range, analogs, calibration factor and evidence."""
        t = self._find(task_ref)
        if not t:
            return "Task not found."
        b = self.db.scalar(select(TaskAIBaseline).where(TaskAIBaseline.task_id == t.id))
        if not b:
            return f"'{t.title}' was added manually ({t.min_hours}-{t.max_hours} h); no AI provenance."
        pv = b.provenance or {}
        cal = pv.get("calibration") or {}
        parts = [f"'{t.title}': raw LLM {b.raw_min:g}-{b.raw_max:g} h (median of {len(pv.get('raw', {}).get('samples', []))} samples)."]
        if cal:
            parts.append(f"Calibration x{cal.get('factor', 1):.2f} from {cal.get('scope_used')} "
                         f"(n_edit={cal.get('n_edit')}, n_actual={cal.get('n_actual')}).")
        if pv.get("analogs"):
            parts.append(f"{len(pv['analogs'])} analogs (blend weight {pv.get('blend_weight', 0):.2f}), "
                         f"analog median {pv.get('analog_mid') or 0:.1f} h.")
        parts.append(f"Currently {t.min_hours:g}-{t.max_hours:g} h.")
        return " ".join(parts)

    def find_similar_past_tasks(self, task_ref: str) -> str:
        """Find similar tasks from past finalized/delivered projects with their final and actual hours."""
        t = self._find(task_ref)
        if not t or t.embedding is None:
            return "No similar tasks found."
        cat = self.db.get(TaskCategory, t.category_id).key if t.category_id else "other"
        from app.db.models import Estimate

        pid = self.db.get(Estimate, self.estimate_id).project_id
        analogs = find_analogs(self.db, list(t.embedding), cat, exclude_project_id=pid, top_k=5)
        return "\n".join(f"{a.title} ({a.project_name}) sim={a.similarity:.2f} final={a.final_mid} actual={a.actual_mid}"
                         for a in analogs) or "No similar tasks found."

    # ----- proposal-creating -----
    def propose_add_task(self, title: str, min_hours: float, max_hours: float, category_key: str = "other",
                         role_name: str = "Backend", module_name: str = "Additional scope", description: str = "",
                         rationale: str = "") -> str:
        """Propose adding a new task (hours are for one mid-level engineer of the role)."""
        op = pr.add_op(self.db, self._proposal(), "add_task", {
            "title": title, "description": description, "category_key": category_key, "role_name": role_name,
            "module_name": module_name, "min_hours": float(min_hours), "max_hours": float(max(max_hours, min_hours)),
        }, summary=f"Add '{title}' ({min_hours:g}-{max_hours:g} h, {role_name})", rationale=rationale)
        return f"Proposed op {op['id']}"

    def propose_update_task(self, task_ref: str, min_hours: float | None = None, max_hours: float | None = None,
                            title: str | None = None, role_name: str | None = None,
                            category_key: str | None = None, rationale: str = "") -> str:
        """Propose changing hours/title/role/category of an existing task."""
        t = self._find(task_ref)
        if not t:
            return "Task not found."
        changes = {k: v for k, v in {"min_hours": min_hours, "max_hours": max_hours, "title": title,
                                     "role_name": role_name, "category_key": category_key}.items() if v is not None}
        current = {"min_hours": t.min_hours, "max_hours": t.max_hours, "title": t.title}
        changes = {k: v for k, v in changes.items() if k not in current or current[k] != v}
        if not changes:
            return "No change needed: the task already has these values. No proposal created."
        op = pr.add_op(self.db, self._proposal(), "update_task", {
            "task_id": str(t.id), "changes": changes, "before": {"min_hours": t.min_hours, "max_hours": t.max_hours, "title": t.title},
        }, summary=f"Update '{t.title}': {changes}", rationale=rationale)
        return f"Proposed op {op['id']}"

    def propose_remove_task(self, task_ref: str, rationale: str = "") -> str:
        """Propose removing a task from the estimate."""
        t = self._find(task_ref)
        if not t:
            return "Task not found."
        op = pr.add_op(self.db, self._proposal(), "remove_task", {"task_id": str(t.id), "title": t.title,
                                                                  "before": {"min_hours": t.min_hours, "max_hours": t.max_hours}},
                       summary=f"Remove '{t.title}'", rationale=rationale)
        return f"Proposed op {op['id']}"

    def propose_split_task(self, task_ref: str, parts: list[SplitPart], rationale: str = "") -> str:
        """Propose splitting a task into parts (title, min_hours, max_hours). Totals are kept equal to the original."""
        t = self._find(task_ref)
        if not t:
            return "Task not found."
        items = [p if isinstance(p, SplitPart) else SplitPart.model_validate(p) for p in parts]
        if len(items) < 2:
            return "A split needs at least two parts."
        smin = sum(p.min_hours for p in items) or 1.0
        smax = sum(p.max_hours for p in items) or 1.0
        scaled = [{"title": p.title, "min_hours": max(0.25, round(p.min_hours * t.min_hours / smin * 2) / 2),
                   "max_hours": max(0.5, round(p.max_hours * t.max_hours / smax * 2) / 2)} for p in items]
        op = pr.add_op(self.db, self._proposal(), "split_task", {"task_id": str(t.id), "title": t.title, "parts": scaled,
                                                                 "before": {"min_hours": t.min_hours, "max_hours": t.max_hours}},
                       summary=f"Split '{t.title}' into {len(scaled)} tasks (total hours preserved)", rationale=rationale)
        return f"Proposed op {op['id']}: {scaled}"

    def propose_remove_module(self, module_name: str, rationale: str = "") -> str:
        """Propose removing a whole module (and its tasks) by module name."""
        words = set(T.tokens(module_name))
        mods = list(self.db.scalars(select(Module).where(Module.estimate_id == self.estimate_id, Module.removed.is_(False))))
        best = max(mods, key=lambda m: len(words & set(T.tokens(m.name))), default=None)
        if best is None or not words & set(T.tokens(best.name)):
            return f"No module matches '{module_name}'. Modules: {[m.name for m in mods]}"
        op = pr.add_op(self.db, self._proposal(), "remove_module", {"module_id": str(best.id), "title": best.name},
                       summary=f"Remove module '{best.name}'", rationale=rationale)
        return f"Proposed op {op['id']}"

    def propose_bulk_adjust(self, percent: float, role_name: str | None = None, category_key: str | None = None,
                            module_name: str | None = None, rationale: str = "") -> str:
        """Propose changing hours of many tasks by a percentage, filtered by role, category and/or module."""
        changes = pr.bulk_changes(self.db, self.estimate_id, float(percent), role_name, category_key, module_name)
        if not changes:
            return "No tasks match that filter."
        flt = ", ".join(f"{k}={v}" for k, v in {"role": role_name, "category": category_key, "module": module_name}.items() if v)
        op = pr.add_op(self.db, self._proposal(), "bulk_adjust", {"percent": percent, "filter": flt, "changes": changes},
                       summary=f"{'+' if percent >= 0 else ''}{percent:g}% hours on {len(changes)} tasks ({flt or 'all'})",
                       rationale=rationale)
        return f"Proposed op {op['id']} affecting {len(changes)} tasks"

    def propose_add_module(self, name: str, description: str = "", rationale: str = "") -> str:
        """Propose adding a new module."""
        op = pr.add_op(self.db, self._proposal(), "add_module", {"name": name, "description": description},
                       summary=f"Add module '{name}'", rationale=rationale)
        return f"Proposed op {op['id']}"

    def all(self) -> list:
        fns = [self.list_tasks, self.get_task_details, self.explain_task, self.find_similar_past_tasks,
               self.propose_add_task, self.propose_update_task, self.propose_remove_task, self.propose_split_task,
               self.propose_bulk_adjust, self.propose_add_module, self.propose_remove_module]
        return [_safe(f) for f in fns]


def _safe(fn):
    """Return tool errors to the model as text instead of aborting the agent run."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            return f"Tool error: {getattr(e, 'message', None) or type(e).__name__}"

    return wrapper


def system_prompt(db: Session, estimate_id: uuid.UUID) -> str:
    rules = active_rules(db)
    edit, actual = load_stats(db)
    cats = {c for (c,) in db.execute(select(TaskCategory.key).join(Task, Task.category_id == TaskCategory.id)
                                     .where(Task.estimate_id == estimate_id))}
    lines = []
    for c in sorted(cats):
        e = edit.get(("category", c))
        a = actual.get(("category", c))
        if e or a:
            lines.append(f"- {c}: edit x{math.exp(e.shrunk_mean) if e else 1:.2f} (n={e.n if e else 0}), "
                         f"actual x{math.exp(a.shrunk_mean) if a else 1:.2f} (n={a.n if a else 0})")
    return render("chat_agent", rules="\n".join(f"- {r.text}" for r in rules) or "none",
                  calibration="\n".join(lines) or "no history yet")


ROLE_ALIASES = {"backend": "Backend", "frontend": "Frontend", "qa": "QA", "design": "Designer", "designer": "Designer",
                "devops": "DevOps", "pm": "PM", "mobile": "Mobile", "ml": "ML/CV Engineer", "data": "Data Engineer"}


def fake_agent(tools: AgentTools, text: str) -> str:
    """Deterministic command interpreter used when no live LLM is available."""
    out: list[str] = []
    low = text.lower()
    for clause in re.split(r"\band\b|;|\n", low):
        clause = clause.strip()
        m = re.search(r"(increase|raise|decrease|reduce|cut)\s+(\w+(?:/\w+)?)?\s*(?:tasks?\s+)?hours?\s+by\s+(\d+(?:\.\d+)?)\s*%", clause)
        if m:
            pct = float(m.group(3)) * (1 if m.group(1) in ("increase", "raise") else -1)
            word = (m.group(2) or "").strip()
            role = ROLE_ALIASES.get(word)
            cat = word if word in T.CATEGORY_INFO else None
            out.append(tools.propose_bulk_adjust(pct, role_name=role, category_key=cat,
                                                 rationale=f"Requested: {clause}"))
            continue
        m = re.search(r"add (?:an? )?(.+?) task", clause) or re.search(r"add (?:an? )?(.+)$", clause)
        if m:
            name = m.group(1).strip()
            cat = T.classify(name)
            idx = T.pick_template(cat, name)
            title = T.TEMPLATES[cat][idx][0] if cat != "other" else name.capitalize()
            base = T.CATEGORY_INFO[cat]["base"] * T.TEMPLATES[cat][idx][2]
            _, actual = load_stats(tools.db)
            a = actual.get(("category", cat))
            f = math.exp(a.shrunk_mean) if a else 1.0
            out.append(tools.propose_add_task(title, round(base * 0.8 * f * 2) / 2, round(base * 1.3 * f * 2) / 2,
                                              category_key=cat, role_name=T.CATEGORY_INFO[cat]["role"],
                                              rationale=f"Requested by PM; sized from category history (x{f:.2f})."))
            continue
        m = re.search(r"(?:remove|delete|drop) (?:the )?(.+?)(?: task)?$", clause)
        if m:
            out.append(tools.propose_remove_task(m.group(1), rationale=f"Requested: {clause}"))
            continue
        m = re.search(r"(?:explain|why)\s+(?:is\s+)?(?:the\s+)?(.+?)(?:\s+task)?\??$", clause)
        if m:
            out.append(tools.explain_task(m.group(1)))
            continue
        if "list" in clause:
            out.append(tools.list_tasks())
    if not out:
        return ("Offline agent (LLM_MODE=fake/replay). Try: \"increase backend hours by 20% and add an SSO task\", "
                "\"remove the push notifications task\", \"explain CRM integration\".")
    created = [o for o in out if o.startswith("Proposed op")]
    head = f"I created {len(created)} proposed change(s) for your review. " if created else ""
    return head + "\n".join(o for o in out if not o.startswith("Proposed op"))


def _cassette_for(db: Session, estimate_id: uuid.UUID, text: str):
    """In replay mode, a recorded live agent conversation with the same prompt is replayed (no network)."""
    from app.agents.cassettes import cassette_dir, replay_model

    d = cassette_dir()
    if not d.exists():
        return None
    for p in sorted(d.glob("*.json")):
        if json.loads(p.read_text()).get("prompt", "").strip().lower() == text.strip().lower():
            titles = {t.title: str(t.id) for t in db.scalars(select(Task).where(Task.estimate_id == estimate_id))}
            return replay_model(p.stem, titles)
    return None


def stream_agent(db: Session, estimate_id: uuid.UUID, session_id: uuid.UUID | None, text: str,
                 user_id: uuid.UUID | None, *, model=None, callbacks: list | None = None) -> Iterator[str]:
    """`model` overrides the LLM (cassette replay in tests); otherwise live/record use the gateway's chat model."""
    session = db.get(AgentSession, session_id) if session_id else None
    if session is None:
        session = AgentSession(estimate_id=estimate_id, mode="chat", created_by=user_id)
        db.add(session)
        db.flush()
    yield sse("session", {"session_id": str(session.id)})
    history = list(db.scalars(select(AgentMessage).where(AgentMessage.session_id == session.id)
                              .order_by(AgentMessage.created_at)))
    db.add(AgentMessage(session_id=session.id, role="user", content=text))
    db.flush()
    tools = AgentTools(db, estimate_id, session.id)
    gw = get_gateway()
    reply = ""
    tool_calls: list[dict] = []
    if model is None and gw.mode == "replay":
        model = _cassette_for(db, estimate_id, text)
    try:
        if model is not None or gw.mode in ("live", "record"):
            from langchain.agents import create_agent
            from langchain_core.messages import AIMessage, ToolMessage

            agent = create_agent(model or gw.chat_model(), tools=tools.all(),
                                 system_prompt=system_prompt(db, estimate_id))
            msgs = [{"role": m.role, "content": m.content} for m in history if m.role in ("user", "assistant")]
            msgs.append({"role": "user", "content": text})
            last_id = None
            for chunk, _meta in agent.stream({"messages": msgs}, stream_mode="messages",
                                             config={"callbacks": callbacks or []}):
                if isinstance(chunk, AIMessage):  # chunks when streaming, whole messages otherwise
                    content = chunk.content if isinstance(chunk.content, str) else "".join(
                        c.get("text", "") for c in chunk.content if isinstance(c, dict))
                    if content:
                        if last_id is not None and chunk.id != last_id and reply:
                            content = "\n\n" + content  # separate text from successive model turns
                        last_id = chunk.id
                        reply += content
                        yield sse("token", {"text": content})
                elif isinstance(chunk, ToolMessage):
                    tool_calls.append({"name": chunk.name, "result": str(chunk.content)[:500]})
                    yield sse("tool", {"name": chunk.name})
                    if (chunk.name or "").startswith("propose_") and tools.proposal is not None:
                        db.flush()
                        yield sse("proposal", proposal_dict(tools.proposal))
        else:
            reply = fake_agent(tools, text)
            for word in re.split(r"(\s+)", reply):
                if word:
                    yield sse("token", {"text": word})
        if tools.proposal is not None:
            yield sse("proposal", proposal_dict(tools.proposal))
        db.add(AgentMessage(session_id=session.id, role="assistant", content=reply, tool_calls=tool_calls))
        db.commit()
        yield sse("done", {"proposal_id": str(tools.proposal.id) if tools.proposal else None})
    except Exception as e:
        db.rollback()
        log.exception("agent failed")
        yield sse("error", {"message": getattr(e, "message", None) or f"{type(e).__name__}"})


def proposal_dict(p) -> dict:
    return {"id": str(p.id), "estimate_id": str(p.estimate_id), "status": p.status, "ops": p.ops,
            "rationale": p.rationale, "created_at": p.created_at}
