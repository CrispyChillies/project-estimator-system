"""Replays live-recorded agent cassettes (no network) and checks the proposal/edit-log invariants."""

import json
import math
import uuid

import pytest
from sqlalchemy import select

from app.agents.cassettes import cassette_dir, replay_model
from app.agents.chat_agent import stream_agent
from app.core.config import get_settings
from app.db.models import ChangeProposal, DeliveryRole, EditEvent, Module, Project, Task
from app.services import proposals as pr
from app.services.documents import ingest
from app.services.generation import generate

pytestmark = pytest.mark.skipif(not (cassette_dir() / "bulk_backend.json").exists(), reason="no cassettes recorded")


def _estimate(db):
    p = Project(name="cassette test", status="draft", data_source="synthetic")
    db.add(p)
    db.commit()
    doc = ingest(db, p.id, "demo_brief_2.md", (get_settings().fixtures_dir / "demo_brief_2.md").read_bytes(), None)
    est = generate(db, p.id, [doc.id], False, None)
    db.commit()
    return est


def _snapshot(db, est_id):
    return sorted((str(t.id), t.min_hours, t.max_hours, t.removed, t.enabled, t.title)
                  for t in db.scalars(select(Task).where(Task.estimate_id == est_id)))


def _run(db, est, name):
    tasks = list(db.scalars(select(Task).where(Task.estimate_id == est.id)))
    before = _snapshot(db, est.id)
    events = list(stream_agent(db, est.id, None, f"cassette:{name}", None,
                               model=replay_model(name, {t.title: str(t.id) for t in tasks})))
    assert not [e for e in events if e.startswith("event: error")], events
    # Invariant: tools only create pending proposals; the estimate is unchanged until a user accepts.
    assert _snapshot(db, est.id) == before
    assert db.scalar(select(EditEvent.id).where(EditEvent.estimate_id == est.id)) is None
    props = list(db.scalars(select(ChangeProposal).where(ChangeProposal.estimate_id == est.id,
                                                         ChangeProposal.status == "pending")))
    return events, [op for p in props for op in p.ops], props


def test_bulk_adjust_respects_role_filter_and_logs_agent_events(db):
    est = _estimate(db)
    _, ops, props = _run(db, est, "bulk_backend")
    op = next(o for o in ops if o["type"] == "bulk_adjust")
    backend = db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == "Backend"))
    changed = [db.get(Task, uuid.UUID(c["task_id"])) for c in op["payload"]["changes"]]
    assert changed and all(t.delivery_role_id == backend for t in changed)
    pr.resolve_op(db, props[0].id, op["id"], True, None)
    db.commit()
    evs = list(db.scalars(select(EditEvent).where(EditEvent.proposal_id == props[0].id)))
    assert len(evs) == len(changed) and all(e.actor == "agent" and e.event_type == "hours_changed" for e in evs)
    for c in op["payload"]["changes"]:
        assert db.get(Task, uuid.UUID(c["task_id"])).max_hours == c["new_max"]


def test_split_preserves_total_hours(db):
    est = _estimate(db)
    _, ops, props = _run(db, est, "split_payments")
    op = next(o for o in ops if o["type"] == "split_task")
    orig = db.get(Task, uuid.UUID(op["payload"]["task_id"]))
    parts = op["payload"]["parts"]
    n = len(parts)
    assert abs(sum(p["min_hours"] for p in parts) - orig.min_hours) <= 0.5 * n
    assert abs(sum(p["max_hours"] for p in parts) - orig.max_hours) <= 0.5 * n
    pr.resolve_op(db, props[0].id, op["id"], True, None)
    db.commit()
    db.refresh(orig)
    assert orig.removed and db.get(Task, orig.id) is not None  # soft removal


def test_remove_module_is_soft_and_reject_is_logged(db):
    est = _estimate(db)
    _, ops, props = _run(db, est, "remove_module")
    op = next(o for o in ops if o["type"] == "remove_module")
    pr.resolve_op(db, props[0].id, op["id"], False, None, "keep it")
    db.commit()
    ev = db.scalar(select(EditEvent).where(EditEvent.proposal_id == props[0].id))
    assert ev.event_type == "proposal_op_rejected" and ev.actor == "user" and ev.reason_text == "keep it"
    assert not db.get(Module, uuid.UUID(op["payload"]["module_id"])).removed


def test_hostile_pasted_instructions_cause_no_mutation_or_removal_proposal(db):
    est = _estimate(db)
    _, ops, _ = _run(db, est, "hostile")
    assert not [o for o in ops if o["type"] in ("remove_task", "remove_module", "bulk_adjust")]


def test_vague_request_is_bounded(db):
    est = _estimate(db)
    _, ops, _ = _run(db, est, "vague")
    assert len(ops) <= 1
    for o in ops:
        assert o["rationale"]
        if o["type"] == "bulk_adjust":
            assert -30 <= o["payload"]["percent"] < 0


def test_noop_update_creates_no_proposal(db):
    est = _estimate(db)
    _, ops, _ = _run(db, est, "qa_min_hours")
    assert not [o for o in ops if o["type"] == "update_task"]


@pytest.mark.parametrize("name", ["add_sso", "explain_integration", "similar_reporting"])
def test_other_scenarios_replay_cleanly(db, name):
    est = _estimate(db)
    events, ops, _ = _run(db, est, name)
    assert any(e.startswith("event: token") for e in events)
    # Incremental streaming was observed in the live recording: many token events per model turn.
    rec = json.loads((cassette_dir() / f"{name}.json").read_text())
    assert rec["sse_token_events"] > 3 * len(rec["messages"])
    if name == "add_sso":
        assert any(o["type"] == "add_task" and math.isfinite(o["payload"]["min_hours"]) for o in ops)
    else:
        assert not ops
