"""Load historical projects (synthetic or dataset) through the same service layer used by the app,
so edit events, baselines and learning updates are produced exactly as in real use."""

from __future__ import annotations

import logging
import statistics
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.datasets.synthetic import SynthProject
from app.db.models import (
    CalibrationRun,
    Document,
    Estimate,
    LLMRawEstimate,
    Project,
    TaskActual,
    TaskAIBaseline,
    UnplannedActual,
    User,
)
from app.llm.gateway import get_gateway
from app.prompts import PROMPT_VERSIONS
from app.services import estimates as es
from app.services.documents import add_chunks
from app.services.learning import deliver_project, finalize_estimate
from app.services.reference import HISTORY_EMAIL, category_maps, role_maps
from app.services.summary import compute_summary

log = logging.getLogger(__name__)


def _llm_raw(sp: SynthProject, k: int) -> dict[str, list[tuple[float, float]]]:
    """Raw estimates from the configured model for the fixed task list (estimation step only)."""
    from app.agents.chains import run_estimation

    tasks = [{"key": t.key, "title": t.title, "description": t.description, "category_key": t.category,
              "role_name": t.role} for t in sp.tasks if t.origin == "ai"]
    summary = sp.brief.splitlines()[2] if len(sp.brief.splitlines()) > 2 else sp.name
    _, samples = run_estimation(tasks, summary, [], k)
    return samples


def load_project(db: Session, sp: SynthProject, data_source: str, *, model_label: str | None = None,
                 k: int = 3) -> Project | None:
    gw = get_gateway()
    key = gw.model_key
    exists = db.scalar(select(Project.id).join(Estimate, Estimate.project_id == Project.id)
                       .where(Project.name == sp.name, Project.data_source == data_source, Estimate.model_key == key))
    if exists:
        return None
    # fake mode keeps the simulator's raw estimates; live/record/replay asks the model (cached in fixtures)
    live_samples = _llm_raw(sp, k) if gw.mode != "fake" else None
    model_label = model_label or (gw.model if live_samples is not None else "synthetic-raw-llm")
    hist = db.scalar(select(User).where(User.email == HISTORY_EMAIL))
    actor = es.Actor("user", hist.id if hist else None)
    _, cat2id = category_maps(db)
    _, role2id = role_maps(db)
    p = Project(name=sp.name, client_name=sp.client, domain=sp.domain, description=sp.brief[:500], status="draft",
                data_source=data_source, started_at=sp.started_at, created_by=actor.user_id,
                tech_tags=[], is_archive=data_source != "user")
    db.add(p)
    db.flush()
    doc = Document(project_id=p.id, filename="brief.md", mime="text/markdown", extracted_text=sp.brief,
                   uploaded_by=actor.user_id)
    db.add(doc)
    db.flush()
    add_chunks(db, doc, sp.brief)
    est = Estimate(project_id=p.id, version=1, status="draft", source="ai", learning_enabled=False,
                   created_by=actor.user_id, model_key=key,
                   model_snapshot={"model": model_label, "model_key": key, "llm_mode": gw.mode,
                                   "prompt_versions": PROMPT_VERSIONS,
                                   "note": f"{data_source} history: actuals and PM edits simulated; raw from {model_label}"})
    db.add(est)
    db.flush()
    vecs = get_gateway().embed([f"{t.title}\n{t.description}" for t in sp.tasks])
    modules: dict[str, object] = {}
    created = []
    for t, vec in zip(sp.tasks, vecs, strict=True):
        if t.module not in modules:
            modules[t.module] = es.create_module(db, est.id, t.module, es.SYSTEM, log=False)
        m = modules[t.module]
        if t.origin != "ai":
            created.append((t, None))
            continue
        sim_samples = t.raw_samples
        samples = (live_samples.get(t.key) or sim_samples) if live_samples is not None else sim_samples
        rmin = statistics.median(s[0] for s in samples)
        rmax = statistics.median(s[1] for s in samples)
        if live_samples is not None and t.final is not None:
            # keep the planted PM behaviour as a ratio to whatever raw estimate the PM saw
            sim_mid = statistics.median((a + b) / 2 for a, b in sim_samples)
            f = ((t.final[0] + t.final[1]) / 2) / sim_mid
            t.final = (max(0.5, round(rmin * f * 2) / 2), max(0.5, round(rmax * f * 2) / 2))
        task = es.create_task(db, est.id, {
            "module_id": m.id, "title": t.title, "description": t.description, "category_id": cat2id.get(t.category),
            "delivery_role_id": role2id.get(t.role), "min_hours": rmin, "max_hours": rmax, "ai_key": t.key,
            "embedding": vec, "rationale": "Historical AI baseline",
        }, es.SYSTEM, origin="ai", log=False)
        db.add(TaskAIBaseline(task_id=task.id, estimate_id=est.id, ai_key=t.key, raw_min=rmin, raw_max=rmax,
                              applied_factor=1.0, shown_min=rmin, shown_max=rmax, category_key=t.category,
                              provenance={"raw": {"min": rmin, "max": rmax, "samples": [list(s) for s in samples]},
                                          "analogs": [], "calibration": None, "learning": False, "rules_applied": []},
                              prompt_version=PROMPT_VERSIONS["estimation"], model=model_label, model_key=key))
        for i, (a, b) in enumerate(samples):
            db.add(LLMRawEstimate(project_id=p.id, task_key=t.key, run_idx=i, prompt_version=PROMPT_VERSIONS["estimation"],
                                  model=model_label, model_key=key, raw_min=a, raw_max=b))
        created.append((t, task))
    db.flush()
    # Historical PM edits, through the service layer => edit_events with actor=user (Historical team)
    for t, task in created:
        if task is None:
            assert t.final is not None
            task = es.create_task(db, est.id, {
                "module_id": modules[t.module].id, "title": t.title, "description": t.description,
                "category_id": cat2id.get(t.category), "delivery_role_id": role2id.get(t.role),
                "min_hours": t.final[0], "max_hours": t.final[1], "embedding": vecs[sp.tasks.index(t)],
            }, actor, origin="user", reason_tag=t.reason_tag)
        elif t.final is None:
            es.remove_task(db, task.id, actor, reason_tag=t.reason_tag)
        elif (t.final[0], t.final[1]) != (task.min_hours, task.max_hours):
            es.update_task(db, task.id, {"min_hours": t.final[0], "max_hours": t.final[1]}, actor, reason_tag=t.reason_tag)
        if t.actual is not None and t.final is not None:
            db.add(TaskActual(task_id=task.id, actual_hours=t.actual, source="dataset", recorded_by=actor.user_id))
    for title, cat, hours in sp.unplanned:
        if hours > 0:
            db.add(UnplannedActual(project_id=p.id, title=title, category_id=cat2id.get(cat), hours=hours))
    db.flush()
    compute_summary(db, est.id)
    finalize_estimate(db, est.id, actor.user_id, run_lessons=False)
    est.finalized_at = sp.started_at + timedelta(days=10)
    deliver_project(db, p.id, run_lessons=False)
    p.delivered_at = sp.delivered_at
    db.execute(update(CalibrationRun).where(CalibrationRun.project_id == p.id, CalibrationRun.trigger == "estimate_finalized")
               .values(created_at=est.finalized_at))
    db.execute(update(CalibrationRun).where(CalibrationRun.project_id == p.id, CalibrationRun.trigger == "project_delivered")
               .values(created_at=sp.delivered_at))
    db.flush()
    return p
