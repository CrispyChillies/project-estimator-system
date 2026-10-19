import uuid

import pytest
from sqlalchemy import select

from app.core.errors import Conflict
from app.db.models import EditEvent, Module, Project, Task, User
from app.services import estimates as es
from app.services.documents import ingest
from app.services.generation import generate
from app.services.operations import OperationExecutor, included_total

BRIEF = b"- Admin panel to manage users.\n- Email notifications.\n- Reporting dashboard.\n"


def _setup(db):
    p = Project(name="ops", status="draft", data_source="user")
    db.add(p)
    db.commit()
    doc = ingest(db, p.id, "b.md", BRIEF, None)
    est = generate(db, p.id, [doc.id], True, None)
    db.commit()
    u = db.scalar(select(User).where(User.email == "alice@calibr.local"))
    tasks = list(db.scalars(select(Task).where(Task.estimate_id == est.id, Task.removed.is_(False))))
    return est, u, tasks


def test_apply_logs_events_with_ids_and_undo_restores(db):
    est, u, tasks = _setup(db)
    t = tasks[0]
    before = included_total(db, est.id)
    ex = OperationExecutor(db, est.id, user_id=u.id, session_id=None)
    batch = uuid.uuid4()
    ops = [{"op": "update_task", "task_id": str(t.id), "changes": {"min_hours": 1, "max_hours": 2}},
           {"op": "remove_task", "task_id": str(tasks[1].id)},
           {"op": "create_task", "module_id": str(t.module_id), "title": "SSO", "min_hours": 12, "max_hours": 20}]
    pv = ex.preview(ops)
    assert pv["before"] == before and pv["deletes"] == 1
    assert included_total(db, est.id) == before  # preview persisted nothing
    rec = ex.apply(ex.record("bulk", {}, ops, batch_id=batch))
    db.commit()
    assert rec.status == "applied" and len(rec.inverse_ops) == 3
    evs = list(db.scalars(select(EditEvent).where(EditEvent.operation_id == rec.id)))
    assert len(evs) == 3 and all(e.batch_id == batch and e.actor == "agent" for e in evs)
    n_events = db.query(EditEvent).count()

    res = ex.undo_batch(batch)
    db.commit()
    assert res[0]["applied"] == 3 and not res[0]["partial"]
    assert included_total(db, est.id) == before
    assert db.query(EditEvent).count() > n_events  # undo appends, never edits
    assert all(e.event_type for e in db.scalars(select(EditEvent).where(EditEvent.operation_id == rec.id)))


def test_undo_skips_rows_user_edited_after(db):
    est, u, tasks = _setup(db)
    a, b = tasks[0], tasks[1]
    ex = OperationExecutor(db, est.id, user_id=u.id)
    rec = ex.apply(ex.record("set_hours", {}, [
        {"op": "update_task", "task_id": str(a.id), "changes": {"min_hours": 3, "max_hours": 4}},
        {"op": "update_task", "task_id": str(b.id), "changes": {"min_hours": 5, "max_hours": 6}}],
        batch_id=uuid.uuid4()))
    db.commit()
    es.update_task(db, a.id, {"max_hours": 9}, es.Actor("user", u.id))
    db.commit()
    res = ex.undo(rec)
    db.commit()
    assert res["partial"] and res["skipped"][0]["task_id"] == str(a.id) and res["applied"] == 1
    db.refresh(a)
    assert a.max_hours == 9


def test_failed_op_rolls_back_atomically(db):
    est, u, tasks = _setup(db)
    before = included_total(db, est.id)
    ex = OperationExecutor(db, est.id, user_id=u.id)
    rec = ex.apply(ex.record("x", {}, [
        {"op": "update_task", "task_id": str(tasks[0].id), "changes": {"min_hours": 1, "max_hours": 1}},
        {"op": "update_task", "task_id": str(uuid.uuid4()), "changes": {"min_hours": 1}}], batch_id=uuid.uuid4()))
    db.commit()
    assert rec.status == "failed" and rec.result["error"] == "task_not_found"
    assert included_total(db, est.id) == before


def test_row_version_optimistic_lock(db):
    est, u, tasks = _setup(db)
    t = tasks[0]
    v = t.row_version
    es.update_task(db, t.id, {"max_hours": t.max_hours + 1}, es.Actor("user", u.id), expected_version=v)
    assert t.row_version == v + 1
    with pytest.raises(Conflict):
        es.update_task(db, t.id, {"max_hours": t.max_hours + 1}, es.Actor("user", u.id), expected_version=v)


def test_remove_module_undo_restores_tasks(db):
    est, u, tasks = _setup(db)
    m = db.get(Module, tasks[0].module_id)
    before = included_total(db, est.id)
    ex = OperationExecutor(db, est.id, user_id=u.id)
    rec = ex.apply(ex.record("delete", {}, [{"op": "remove_module", "module_id": str(m.id)}], batch_id=uuid.uuid4()))
    db.commit()
    assert included_total(db, est.id) != before
    ex.undo(rec)
    db.commit()
    assert included_total(db, est.id) == before
