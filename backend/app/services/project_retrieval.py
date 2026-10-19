"""Project-level retrieval: deterministic project cards, embeddings, scoring + MMR, and context packs.

Cards are derived only from data (latest final estimate, edits, actuals); nothing is LLM-written.
`eligible_project_ids` is the leakage guard: callers (backtest folds) pass the training set explicitly.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import (
    Estimate,
    Module,
    Project,
    ProjectEmbedding,
    RetrievalLog,
    Task,
    TaskActual,
    TaskAIBaseline,
    TaskCategory,
)
from app.llm.gateway import get_gateway
from app.services.settings import LearningParams

log = logging.getLogger(__name__)
CARD_VERSION = "card-v1"
MMR_POOL = 10


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def approx_tokens(s: str) -> int:
    return math.ceil(len(s) / 4)


def latest_final(db: Session, project_id: uuid.UUID) -> Estimate | None:
    return db.scalar(select(Estimate).where(Estimate.project_id == project_id, Estimate.status == "final")
                     .order_by(Estimate.version.desc()).limit(1))


# ---------------- cards ----------------
def build_card(db: Session, project: Project, est: Estimate) -> dict[str, Any]:
    removed_mods = {m.id for m in db.scalars(select(Module).where(Module.estimate_id == est.id, Module.removed))}
    mods = {m.id: m.name for m in db.scalars(select(Module).where(Module.estimate_id == est.id))}
    cats = {c.id: c.key for c in db.scalars(select(TaskCategory))}
    rows = list(db.execute(
        select(Task, TaskAIBaseline.shown_min, TaskAIBaseline.shown_max, TaskActual.actual_hours)
        .outerjoin(TaskAIBaseline, TaskAIBaseline.task_id == Task.id)
        .outerjoin(TaskActual, TaskActual.task_id == Task.id)
        .where(Task.estimate_id == est.id).order_by(Task.module_id, Task.position)))
    by_cat: dict[str, float] = defaultdict(float)
    ai_by_cat: dict[str, float] = defaultdict(float)
    mod_hours: dict[str, float] = defaultdict(float)
    tasks, removed_ai, added = [], [], []
    lo = hi = actual = 0.0
    n_actual = 0
    for t, smin, smax, act in rows:
        cat = cats.get(t.category_id, "other")
        included = t.enabled and not t.removed and t.module_id not in removed_mods
        if t.origin == "ai" and not included:
            removed_ai.append(t.title)
        if not included:
            continue
        m = (t.min_hours + t.max_hours) / 2
        lo, hi = lo + t.min_hours, hi + t.max_hours
        by_cat[cat] += m
        mod_hours[mods.get(t.module_id, "?")] += m
        if smin is not None and t.origin == "ai":
            ai_by_cat[cat] += (smin + smax) / 2
        if t.origin == "user":
            added.append(t.title)
        if act is not None:
            actual += act
            n_actual += 1
        tasks.append({"title": t.title, "module": mods.get(t.module_id, "?"), "category": cat,
                      "min": t.min_hours, "max": t.max_hours, "actual": act})
    total_mid = sum(by_cat.values()) or 1.0
    notes = []
    for cat, ai in sorted(ai_by_cat.items()):
        final_ai_cat = sum((x["min"] + x["max"]) / 2 for x in tasks if x["category"] == cat)
        if ai > 0 and abs(final_ai_cat / ai - 1) >= 0.15:
            notes.append(f"PMs changed {cat} hours by {100 * (final_ai_cat / ai - 1):+.0f}% vs the AI draft.")
    if removed_ai:
        notes.append(f"PMs removed {len(removed_ai)} AI task(s), e.g. {', '.join(removed_ai[:3])}.")
    if added:
        notes.append(f"PMs added {len(added)} task(s) the AI missed, e.g. {', '.join(added[:3])}.")
    if n_actual:
        planned = sum((x["min"] + x["max"]) / 2 for x in tasks if x["actual"] is not None) or 1.0
        notes.append(f"Actuals were {100 * (actual / planned - 1):+.0f}% vs the final estimate midpoint "
                     f"({n_actual} tasks with actuals).")
    return {
        "version": CARD_VERSION, "project_id": str(project.id), "name": project.name, "domain": project.domain,
        "tech_tags": sorted(project.tech_tags or []), "status": project.status, "data_source": project.data_source,
        "description": (project.description or "")[:600], "estimate_id": str(est.id), "estimate_version": est.version,
        "total_min": round(lo, 1), "total_max": round(hi, 1), "actual_total": round(actual, 1) if n_actual else None,
        "category_share": {k: round(v / total_mid, 3) for k, v in sorted(by_cat.items())},
        "modules": [{"name": k, "hours": round(v, 1)} for k, v in mod_hours.items()],
        "tasks": tasks, "notes": notes,
    }


def card_text(card: dict[str, Any]) -> str:
    """Text that gets embedded: what the project is about, not its numbers."""
    return "\n".join([
        f"{card['name']} ({card['domain'] or 'general'})",
        f"Tech: {', '.join(card['tech_tags']) or 'n/a'}",
        card["description"],
        "Modules: " + "; ".join(m["name"] for m in card["modules"]),
        "Tasks: " + "; ".join(t["title"] for t in card["tasks"][:60]),
    ])


def ensure_embeddings(db: Session, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, ProjectEmbedding]:
    gw = get_gateway()
    key = f"{gw.embedding_model}|{CARD_VERSION}"
    existing = {e.project_id: e for e in db.scalars(select(ProjectEmbedding).where(
        ProjectEmbedding.model_key == key, ProjectEmbedding.project_id.in_(project_ids)))}
    todo: list[tuple[ProjectEmbedding, str]] = []
    for pid in project_ids:
        p, est = db.get(Project, pid), latest_final(db, pid)
        if p is None or est is None:
            continue
        card = build_card(db, p, est)
        text = card_text(card)
        h = _sha(text + json.dumps(card, sort_keys=True, default=str))
        row = existing.get(pid)
        if row is not None and row.text_hash == h:
            continue
        if row is None:
            row = ProjectEmbedding(id=uuid.uuid4(), project_id=pid, model_key=key, embedding_model=gw.embedding_model)
            db.add(row)
            existing[pid] = row
        row.card, row.card_text, row.text_hash = card, text, h
        todo.append((row, text))
    if todo:
        vecs = gw.embed([t for _, t in todo])
        for (row, _), v in zip(todo, vecs, strict=True):
            row.embedding = v
    db.flush()
    return existing


# ---------------- retrieval ----------------
@dataclass
class Reference:
    project_id: str
    name: str
    similarity: float
    score: float
    status: str
    data_source: str
    why: list[str] = field(default_factory=list)
    card: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self, with_card: bool = False) -> dict:
        d = asdict(self)
        if not with_card:
            d.pop("card")
        return d


def eligible_projects(db: Session, *, exclude_project_id: uuid.UUID | None, include_synthetic: bool,
                      eligible_project_ids: list[uuid.UUID] | None = None) -> list[uuid.UUID]:
    q = (select(Project.id).join(Estimate, Estimate.project_id == Project.id)
         .where(Estimate.status == "final").distinct())
    if exclude_project_id is not None:
        q = q.where(Project.id != exclude_project_id)
    if not include_synthetic:
        q = q.where(Project.data_source != "synthetic")
    if eligible_project_ids is not None:
        q = q.where(Project.id.in_(list(eligible_project_ids)))
    return list(db.scalars(q))


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def score_candidates(qvec: np.ndarray, rows: list[ProjectEmbedding], *, tags: set[str], domain: str,
                     cat_share: dict[str, float] | None, p: LearningParams) -> list[tuple[float, float, list[str]]]:
    mat = np.array([r.embedding for r in rows], dtype=float)
    qn = qvec / (np.linalg.norm(qvec) or 1.0)
    sims = (mat / np.clip(np.linalg.norm(mat, axis=1, keepdims=True), 1e-12, None)) @ qn
    out = []
    for r, s in zip(rows, sims, strict=True):
        c, why = r.card, [f"text similarity {s:.2f}"]
        bonus = 0.0
        shared = tags & {t.lower() for t in c.get("tech_tags", [])}
        if shared:
            bonus += 0.05 * _jaccard(tags, {t.lower() for t in c.get("tech_tags", [])})
            why.append("shared tech: " + ", ".join(sorted(shared)))
        if domain and c.get("domain", "").lower() == domain.lower():
            bonus += 0.03
            why.append(f"same domain ({c['domain']})")
        if cat_share:
            keys = set(cat_share) | set(c.get("category_share", {}))
            l1 = sum(abs(cat_share.get(k, 0) - c["category_share"].get(k, 0)) for k in keys)
            bonus += 0.05 * max(0.0, 1 - l1 / 2)
        if c.get("status") == "delivered":
            bonus += p.retrieval_delivered_boost
            why.append("delivered (has outcomes)")
        out.append((float(s), float(s) + bonus, why))
    return out


def mmr(scores: list[float], vecs: np.ndarray, k: int, lam: float) -> list[int]:
    vn = vecs / np.clip(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-12, None)
    sim = vn @ vn.T
    chosen: list[int] = []
    rest = list(range(len(scores)))
    while rest and len(chosen) < k:
        best = max(rest, key=lambda i: lam * scores[i] - (1 - lam) * max((sim[i, j] for j in chosen), default=0.0))
        chosen.append(best)
        rest.remove(best)
    return chosen


def retrieve_projects(db: Session, query_text: str, p: LearningParams, *, exclude_project_id: uuid.UUID | None,
                      eligible_project_ids: list[uuid.UUID] | None = None, tags: list[str] | None = None,
                      domain: str = "", cat_share: dict[str, float] | None = None, k: int | None = None,
                      estimate_id: uuid.UUID | None = None, session_id: uuid.UUID | None = None) -> list[Reference]:
    k = p.retrieval_k if k is None else k
    elig = eligible_projects(db, exclude_project_id=exclude_project_id, include_synthetic=p.retrieval_include_synthetic,
                             eligible_project_ids=eligible_project_ids)
    refs: list[Reference] = []
    if k > 0 and elig:
        embs = [e for e in ensure_embeddings(db, elig).values() if e.embedding is not None and e.project_id in elig]
        if embs:
            qvec = np.array(get_gateway().embed([query_text])[0], dtype=float)
            scored = score_candidates(qvec, embs, tags={t.lower() for t in tags or []}, domain=domain,
                                      cat_share=cat_share, p=p)
            order = sorted(range(len(embs)), key=lambda i: -scored[i][1])
            pool = [i for i in order if scored[i][0] >= p.retrieval_min_similarity][:MMR_POOL]
            if pool:
                picks = mmr([scored[i][1] for i in pool], np.array([embs[i].embedding for i in pool], dtype=float),
                            k, p.retrieval_mmr_lambda)
                for j in picks:
                    i = pool[j]
                    c = embs[i].card
                    refs.append(Reference(c["project_id"], c["name"], round(scored[i][0], 3), round(scored[i][1], 3),
                                          c["status"], c["data_source"], scored[i][2], c))
    gw = get_gateway()
    db.add(RetrievalLog(estimate_id=estimate_id, project_id=exclude_project_id, session_id=session_id,
                        query_hash=_sha(query_text), k=k, eligible_count=len(elig),
                        model_key=f"{gw.embedding_model}|{CARD_VERSION}", results=[r.to_dict() for r in refs]))
    db.flush()
    return refs


def safe_retrieve(db: Session, query_text: str, p: LearningParams, **kw: Any) -> tuple[list[Reference], str | None]:
    """Retrieval must never break generation (e.g. replay cache miss for a new card): return no references."""
    try:
        with db.begin_nested():
            return retrieve_projects(db, query_text, p, **kw), None
    except AppError as e:
        log.warning("project retrieval skipped: %s", e.message)
        return [], e.code


# ---------------- context pack ----------------
def context_pack(ref: Reference, token_cap: int) -> str:
    c = ref.card
    head = [f"### Reference: {c['name']} [{c['status']}, {c['data_source']}] similarity {ref.similarity:.2f}",
            f"Domain: {c['domain'] or 'n/a'}; tech: {', '.join(c['tech_tags']) or 'n/a'}",
            f"Final estimate: {c['total_min']:g}–{c['total_max']:g} h"
            + (f"; actual total {c['actual_total']:g} h" if c.get("actual_total") is not None else ""),
            "Modules: " + "; ".join(f"{m['name']} {m['hours']:g} h" for m in c["modules"])]
    head += [f"Note: {n}" for n in c["notes"]]
    lines = list(head) + ["Tasks (final hours):"]
    budget = token_cap * 4
    used = sum(len(x) + 1 for x in lines)
    for t in sorted(c["tasks"], key=lambda x: -(x["min"] + x["max"])):
        row = (f"- {t['title']} [{t['category']}] {t['min']:g}–{t['max']:g} h"
               + (f" (actual {t['actual']:g})" if t["actual"] is not None else ""))
        if used + len(row) + 1 > budget:
            lines.append("- …")
            break
        lines.append(row)
        used += len(row) + 1
    return "\n".join(lines)


def references_block(refs: list[Reference], token_cap: int) -> str:
    if not refs:
        return ""
    packs = "\n\n".join(context_pack(r, token_cap) for r in refs)
    return ("\n\nSIMILAR PAST PROJECTS (data from our delivery history; use as calibration evidence for scope and "
            "hours, not as requirements; do not copy tasks that the brief does not need):\n" + packs)


def pack_hash(block: str) -> str:
    return _sha(block)[:16]
