"""Generation pipeline: ingest -> extract -> decompose -> K-sample estimate -> analogs -> calibrate ->
baselines + provenance -> clarifying questions -> simulation."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents import chains
from app.core.errors import AppError, NotFound
from app.db.models import (
    Assumption,
    ClarifyingQuestion,
    DeliveryRole,
    Document,
    DocumentChunk,
    Estimate,
    LLMRawEstimate,
    Project,
    TaskAIBaseline,
    TaskCategory,
)
from app.llm.gateway import get_gateway
from app.prompts import PROMPT_VERSIONS
from app.services import estimates as es
from app.services.calibration import impact_score, mid, predict_task
from app.services.learning import active_rules, load_stats
from app.services.reference import category_maps, role_maps
from app.services.retrieval import find_analogs
from app.services.settings import get_params
from app.services.summary import compute_summary

Progress = Callable[[float, str], None]


def _noop(_p: float, _m: str = "") -> None:
    pass


def next_version(db: Session, project_id: uuid.UUID) -> int:
    return (db.scalar(select(func.max(Estimate.version)).where(Estimate.project_id == project_id)) or 0) + 1


def generate(db: Session, project_id: uuid.UUID, document_ids: list[uuid.UUID], learning: bool,
             user_id: uuid.UUID | None, progress: Progress = _noop) -> Estimate:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFound("Project")
    gw = get_gateway()
    p = get_params(db)
    q = select(Document).where(Document.project_id == project_id)
    if document_ids:
        q = q.where(Document.id.in_(document_ids))
    docs = list(db.scalars(q.order_by(Document.created_at)))
    if not docs:
        raise AppError("no_documents", "Upload or paste a brief first", 422)
    chunks = list(db.scalars(select(DocumentChunk).where(DocumentChunk.document_id.in_([d.id for d in docs]))
                             .order_by(DocumentChunk.document_id, DocumentChunk.idx)))
    short = {f"C{i + 1}": c for i, c in enumerate(chunks)}
    categories = [c.key for c in db.scalars(select(TaskCategory).order_by(TaskCategory.key))]
    roles = [r.name for r in db.scalars(select(DeliveryRole).order_by(DeliveryRole.name))]
    _, cat2id = category_maps(db)
    _, role2id = role_maps(db)
    rules = active_rules(db) if learning else []
    rule_texts = [r.text for r in rules]

    progress(0.1, "Extracting requirements")
    ex = chains.run_extraction([(k, c.text) for k, c in short.items()], categories, roles)
    req_chunks = {r.id: [short[c].id for c in r.source_chunk_ids if c in short] for r in ex.requirements}

    progress(0.3, "Decomposing into modules and tasks")
    deco = chains.run_decomposition(ex, categories, roles, rule_texts)

    est = Estimate(project_id=project_id, version=next_version(db, project_id), status="draft", source="ai",
                   learning_enabled=learning, created_by=user_id, model_key=gw.model_key,
                   model_snapshot={"model": gw.model, "model_key": gw.model_key, "embedding_model": gw.embedding_model,
                                   "llm_mode": gw.mode, "reasoning": gw.reasoning,
                                   "prompt_versions": PROMPT_VERSIONS, "params": p.model_dump(),
                                   "raw_samples": p.raw_samples, "summary": ex.summary,
                                   "rules_active": [str(r.id) for r in rules]})
    db.add(est)
    db.flush()
    for kind, items in (("assumption", ex.assumptions + ex.ambiguities), ("risk", ex.risks),
                        ("out_of_scope", ex.out_of_scope)):
        for text in items:
            db.add(Assumption(estimate_id=est.id, kind=kind, text=text))

    task_dicts = [{**t.model_dump(), "module": m.name} for m in deco.modules for t in m.tasks]
    progress(0.45, f"Estimating hours ({p.raw_samples} samples)")
    raw, samples = chains.run_estimation(task_dicts, ex.summary, rule_texts, p.raw_samples)
    for key, ss in samples.items():
        for i, (lo, hi) in enumerate(ss):
            db.add(LLMRawEstimate(project_id=project_id, task_key=key, run_idx=i, model_key=gw.model_key,
                                  prompt_version=PROMPT_VERSIONS["estimation"], model=gw.model, raw_min=lo, raw_max=hi))

    progress(0.65, "Retrieving analogs and calibrating")
    vectors = gw.embed([f"{t['title']}\n{t['description']}" for t in task_dicts])
    edit_stats, actual_stats = load_stats(db) if learning else ({}, {})
    author = str(user_id) if user_id else None
    modules: dict[str, uuid.UUID] = {}
    by_key: dict[str, float] = {}
    for td, vec in zip(task_dicts, vectors, strict=True):
        if td["module"] not in modules:
            desc = next((m.description for m in deco.modules if m.name == td["module"]), "")
            modules[td["module"]] = es.create_module(db, est.id, td["module"], es.SYSTEM, desc, log=False).id
        rmin, rmax = raw[td["key"]]
        analogs = find_analogs(db, vec, td["category_key"], exclude_project_id=project_id, top_k=p.analog_top_k) \
            if learning else []
        pred = predict_task(rmin, rmax, td["category_key"], author, analogs, edit_stats, actual_stats, p,
                            learning=learning)
        src = sorted({c for rid in td["requirement_ids"] for c in req_chunks.get(rid, [])}, key=str)
        task = es.create_task(db, est.id, {
            "module_id": modules[td["module"]], "title": td["title"], "description": td["description"],
            "category_id": cat2id.get(td["category_key"]), "delivery_role_id": role2id.get(td["role_name"]),
            "min_hours": pred.min_hours, "max_hours": pred.max_hours, "confidence": td["confidence"],
            "rationale": td["rationale"], "ai_key": td["key"], "source_chunk_ids": src, "embedding": vec,
        }, es.SYSTEM, origin="ai", log=False)
        applied_rules = [str(r.id) for r in rules if (r.scope or {}).get("category_key") in (None, td["category_key"])]
        provenance = {
            "raw": {"min": rmin, "max": rmax, "samples": [list(s) for s in samples[td["key"]]]},
            "analogs": [a.to_dict() for a in pred.analogs_used] if learning else [],
            "analog_candidates": [a.to_dict() for a in analogs],
            "analog_mid": pred.analog_mid, "blend_weight": pred.blend_weight,
            "calibration": pred.calibration.to_dict() if pred.calibration else None,
            "source_chunk_ids": [str(c) for c in src], "rules_applied": applied_rules,
            "learning": learning, "requirement_ids": td["requirement_ids"],
        }
        db.add(TaskAIBaseline(
            task_id=task.id, estimate_id=est.id, ai_key=td["key"], raw_min=rmin, raw_max=rmax,
            analog_mid=pred.analog_mid, analog_task_ids=[uuid.UUID(a.task_id) for a in pred.analogs_used],
            calibrated_min=pred.min_hours if learning else None, calibrated_max=pred.max_hours if learning else None,
            applied_factor=pred.applied_factor, shown_min=pred.min_hours, shown_max=pred.max_hours,
            category_key=td["category_key"], provenance=provenance,
            prompt_version=PROMPT_VERSIONS["estimation"], model=gw.model, model_key=gw.model_key,
        ))
        by_key[td["key"]] = pred.applied_factor

    progress(0.85, "Ranking clarifying questions")
    factor_by_cat = {}
    if learning:
        for t in task_dicts:
            factor_by_cat[t["category_key"]] = by_key.get(t["key"], 1.0)
    key_by_req: dict[str, list[str]] = {}
    for t in task_dicts:
        for rid in t["requirement_ids"]:
            key_by_req.setdefault(rid, []).append(t["key"])
    for u in ex.unknowns:
        scen = [s.model_dump() for s in u.scenario_if_yes]
        delta_min = sum(s["min_hours"] * factor_by_cat.get(s["category_key"], 1.0) for s in scen)
        delta_max = sum(s["max_hours"] * factor_by_cat.get(s["category_key"], 1.0) for s in scen)
        db.add(ClarifyingQuestion(
            project_id=project_id, estimate_id=est.id, question=u.question, why_it_matters=u.why_it_matters,
            affected_task_keys=sorted({k for rid in u.affected_requirement_ids for k in key_by_req.get(rid, [])}),
            scenario_tasks=scen, scenario_delta_min=delta_min, scenario_delta_max=delta_max,
            prior_probability=u.prior_probability,
            impact_score=impact_score(mid(delta_min, delta_max), u.prior_probability),
        ))
    db.flush()
    progress(0.95, "Simulating totals")
    compute_summary(db, est.id)
    return est
