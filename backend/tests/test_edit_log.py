import io
import math

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.errors import AppError
from app.db.models import EditEvent, Estimate, Project, Task, TaskAIBaseline, User
from app.services import actuals as ac
from app.services import estimates as es
from app.services import proposals as pr
from app.services.documents import ingest
from app.services.generation import generate
from app.services.learning import deliver_project, finalize_estimate, load_stats, recompute

BRIEF = b"""We need a web app with login and SSO for staff.
- Admin panel to manage users and catalog.
- Integrate with the client's CRM (HubSpot) to sync contacts.
- Stripe payments for orders.
- Email notifications on order status.
Maybe a recommendation engine later?
"""


def _project(db):
    p = Project(name="Test", status="draft", data_source="user")
    db.add(p)
    db.commit()
    return p


def _generate(db, learning=False):
    p = _project(db)
    doc = ingest(db, p.id, "brief.md", BRIEF, None)
    est = generate(db, p.id, [doc.id], learning, None)
    db.commit()
    return p, est


def _user(db):
    return db.scalar(select(User).where(User.email == "alice@calibr.local"))


def test_generation_creates_baselines_with_provenance(db):
    _, est = _generate(db)
    tasks = list(db.scalars(select(Task).where(Task.estimate_id == est.id)))
    assert tasks and all(t.origin == "ai" and t.ai_key for t in tasks)
    titles = {t.title for t in tasks}
    assert {"CI/CD pipeline", "QA and regression testing", "Project management and communication"} <= titles
    bl = list(db.scalars(select(TaskAIBaseline).where(TaskAIBaseline.estimate_id == est.id)))
    assert len(bl) == len(tasks)
    for b in bl:
        assert len(b.provenance["raw"]["samples"]) == 3
        assert b.shown_min == b.raw_min  # learning off => raw shown
    assert est.summary["simulation"]["p50"] > 0
    assert db.scalar(select(EditEvent).where(EditEvent.estimate_id == est.id)) is None  # generation is not an edit


def test_first_edit_old_value_equals_baseline_and_reason_logged(db):
    _, est = _generate(db)
    u = _user(db)
    t = db.scalars(select(Task).where(Task.estimate_id == est.id)).first()
    b = es.baseline_for(db, t.id)
    es.update_task(db, t.id, {"min_hours": t.min_hours * 2, "max_hours": t.max_hours * 2}, es.Actor("user", u.id),
                   reason_tag="underestimated_complexity")
    db.commit()
    ev = db.scalar(select(EditEvent).where(EditEvent.task_id == t.id))
    assert ev.event_type == "hours_changed" and ev.actor == "user" and ev.user_id == u.id
    assert ev.old_value == {"min": b.shown_min, "max": b.shown_max}
    assert ev.reason_tag == "underestimated_complexity"


def test_edit_and_event_are_atomic(db):
    _, est = _generate(db)
    t = db.scalars(select(Task).where(Task.estimate_id == est.id)).first()
    old = t.min_hours
    with pytest.raises(AppError):
        es.update_task(db, t.id, {"min_hours": old + 1}, es.Actor())
        es.update_task(db, t.id, {"min_hours": 50, "max_hours": 1}, es.Actor())  # invalid -> caller rolls back
    db.rollback()
    db.expire_all()
    assert db.get(Task, t.id).min_hours == old
    assert db.scalar(select(EditEvent).where(EditEvent.task_id == t.id)) is None


def test_edit_events_are_append_only(db):
    _, est = _generate(db)
    t = db.scalars(select(Task).where(Task.estimate_id == est.id)).first()
    es.update_task(db, t.id, {"title": "x"}, es.Actor())
    db.commit()
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE edit_events SET reason_text='tamper'"))
        db.commit()
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE task_ai_baselines SET raw_min=0"))
        db.commit()
    db.rollback()


def test_proposal_accept_and_reject_are_logged(db):
    _, est = _generate(db)
    u = _user(db)
    t1, t2 = list(db.scalars(select(Task).where(Task.estimate_id == est.id)))[:2]
    prop = pr.new_proposal(db, est.id, None, "test")
    op1 = pr.add_op(db, prop, "update_task", {"task_id": str(t1.id), "changes": {"min_hours": 1, "max_hours": 2}}, "u")
    op2 = pr.add_op(db, prop, "remove_task", {"task_id": str(t2.id)}, "r")
    op3 = pr.add_op(db, prop, "add_task", {"title": "SSO", "category_key": "auth", "role_name": "Backend",
                                          "min_hours": 8, "max_hours": 16}, "a")
    db.commit()
    assert db.get(Task, t1.id).min_hours != 1  # proposing never mutates
    pr.resolve_op(db, prop.id, op1["id"], True, u.id)
    pr.resolve_op(db, prop.id, op2["id"], False, u.id, "keep it")
    pr.resolve_op(db, prop.id, op3["id"], True, u.id)
    db.commit()
    assert db.get(Task, t1.id).min_hours == 1
    assert not db.get(Task, t2.id).removed
    evs = list(db.scalars(select(EditEvent).where(EditEvent.proposal_id == prop.id)))
    kinds = {(e.event_type, e.actor) for e in evs}
    assert ("hours_changed", "agent") in kinds and ("task_added", "agent") in kinds
    assert ("proposal_op_rejected", "user") in kinds
    assert db.get(type(prop), prop.id).status == "partial"
    with pytest.raises(AppError):
        pr.resolve_op(db, prop.id, op1["id"], True, u.id)


def test_finalize_updates_edit_stats_idempotently_and_blocks_edits(db):
    _, est = _generate(db)
    u = _user(db)
    tasks = [t for t in db.scalars(select(Task).where(Task.estimate_id == est.id))]
    for t in tasks:
        es.update_task(db, t.id, {"min_hours": t.min_hours * 1.5, "max_hours": t.max_hours * 1.5}, es.Actor("user", u.id))
    finalize_estimate(db, est.id, u.id, run_lessons=False)
    db.commit()
    edit, _ = load_stats(db)
    g = edit[("global", "global")]
    assert g.n == len(tasks)
    assert g.mean == pytest.approx(math.log(1.5), abs=1e-6)
    recompute(db, "manual")
    db.commit()
    edit2, _ = load_stats(db)
    assert edit2[("global", "global")].shrunk_mean == pytest.approx(g.shrunk_mean)
    with pytest.raises(AppError):
        es.update_task(db, tasks[0].id, {"title": "nope"}, es.Actor())
    assert db.get(Estimate, est.id).status == "final"


def test_actuals_csv_validation_and_delivery(db):
    p, est = _generate(db)
    u = _user(db)
    finalize_estimate(db, est.id, u.id, run_lessons=False)
    db.commit()
    tpl = ac.csv_template(db, p.id)
    assert tpl.startswith("task_id,")
    bad = "task_id,actual_hours\nnot-a-task,5\n"
    with pytest.raises(AppError) as e:
        ac.import_csv(db, p.id, bad.encode(), u.id)
    assert e.value.details[0]["error"] == "unknown task"
    rows = list(ac.final_tasks(db, p.id))
    buf = io.StringIO()
    buf.write("task_id,actual_hours\n")
    for t, _, _ in rows:
        buf.write(f"{t.id},{(t.min_hours + t.max_hours)}\n")
    assert ac.import_csv(db, p.id, buf.getvalue().encode(), u.id)["imported"] == len(rows)
    with pytest.raises(AppError):
        ac.import_csv(db, p.id, b"task_id,actual_hours\n" + f"{rows[0][0].id},-3\n".encode(), u.id)
    ac.add_unplanned(db, p.id, "Change request", 10, None)
    deliver_project(db, p.id, run_lessons=False)
    db.commit()
    _, actual = load_stats(db)
    assert actual[("global", "global")].mean == pytest.approx(math.log(2), abs=0.01)
    acc = ac.accuracy(db, p.id)
    assert acc["unplanned_hours"] == 10 and acc["tasks_with_actuals"] == len(rows)


def test_second_generation_uses_learning(db):
    p, est = _generate(db)
    u = _user(db)
    for t in db.scalars(select(Task).where(Task.estimate_id == est.id)):
        es.update_task(db, t.id, {"min_hours": t.min_hours * 2, "max_hours": t.max_hours * 2}, es.Actor("user", u.id))
    finalize_estimate(db, est.id, u.id, run_lessons=False)
    db.commit()
    p2 = _project(db)
    doc = ingest(db, p2.id, "brief.md", BRIEF, None)
    off = generate(db, p2.id, [doc.id], False, u.id)
    on = generate(db, p2.id, [doc.id], True, u.id)
    db.commit()
    assert on.summary["total_mid"] > off.summary["total_mid"] * 1.2
    b = db.scalars(select(TaskAIBaseline).where(TaskAIBaseline.estimate_id == on.id)).first()
    assert b.provenance["calibration"]["n_edit"] > 0
    assert b.provenance["analogs"], "identical tasks from the first project should be analogs"
    assert all(a["project_id"] != str(p2.id) for a in b.provenance["analogs"])
