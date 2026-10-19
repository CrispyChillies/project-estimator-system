from sqlalchemy import select

from app.db.models import EditEvent, Project, Task, TaskAIBaseline, User
from app.services import added_tasks as at
from app.services import estimates as es
from app.services.documents import ingest
from app.services.generation import generate

BRIEF = b"- Admin panel to manage users.\n- Email notifications.\n"


def test_added_tasks_get_ai_estimate_baseline_and_log(db):
    p = Project(name="added", status="draft", data_source="user")
    db.add(p)
    db.commit()
    doc = ingest(db, p.id, "b.md", BRIEF, None)
    est = generate(db, p.id, [doc.id], True, None)
    db.commit()
    u = db.scalar(select(User).where(User.email == "alice@calibr.local"))
    module = db.scalars(select(Task).where(Task.estimate_id == est.id)).first().module_id
    t1 = es.create_task(db, est.id, {"module_id": module, "title": "Push notifications for couriers"}, es.Actor("user", u.id))
    t2 = es.create_task(db, est.id, {"module_id": module, "title": "Stripe payments checkout"}, es.Actor("user", u.id))
    db.commit()
    assert at.pending_task_ids(db, est.id) == [t1.id, t2.id]

    at.estimate_added_tasks(db, est.id, [t1.id, t2.id], u.id, lambda *_: None)
    db.commit()
    for t in (t1, t2):
        db.refresh(t)
        assert t.max_hours > 0 and t.category_id is not None and t.delivery_role_id is not None
        b = db.scalar(select(TaskAIBaseline).where(TaskAIBaseline.task_id == t.id))
        assert b and b.provenance["added_by_pm"] and b.shown_min == t.min_hours
        assert t.origin == "user"  # stays a PM-added task for structural signals
    ev = db.scalar(select(EditEvent).where(EditEvent.task_id == t1.id, EditEvent.event_type == "hours_changed"))
    assert ev.actor == "system" and ev.old_value == {"min": 0.0, "max": 0.0}
    assert at.pending_task_ids(db, est.id) == []  # already estimated; batch does not redo them
