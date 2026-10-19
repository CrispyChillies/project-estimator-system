from sqlalchemy import select

from app.db.models import Project, User
from app.services import actuals as ac
from app.services.analytics import analytics
from app.services.documents import ingest
from app.services.generation import generate
from app.services.learning import deliver_project, finalize_estimate

BRIEF = b"- Admin panel to manage users.\n- Email notifications.\n- Reporting dashboard with charts.\n"


def _delivered(db, owner, name, factor):
    p = Project(name=name, status="draft", data_source="user", owner_id=owner.id)
    db.add(p)
    db.commit()
    doc = ingest(db, p.id, "b.md", BRIEF, owner.id)
    est = generate(db, p.id, [doc.id], True, owner.id)
    finalize_estimate(db, est.id, owner.id, run_lessons=False)
    db.flush()
    for t, _, _ in ac.final_tasks(db, p.id):
        if t.enabled and not t.removed:
            ac.upsert_actual(db, p.id, t.id, (t.min_hours + t.max_hours) / 2 * factor, owner.id)
    ac.add_unplanned(db, p.id, "Extra export", 5, None, reason="change_request")
    deliver_project(db, p.id, run_lessons=False, user_id=owner.id)
    db.commit()
    return p


def test_analytics_scoped_and_not_enough_flags(db):
    u = db.scalar(select(User).where(User.email == "alice@calibr.local"))
    other = db.scalar(select(User).where(User.email == "bob@calibr.local"))
    p1 = _delivered(db, u, "A1", 1.2)
    a = analytics(db, [p1.id])
    assert a["estimate_vs_actual"]["n"] == 1
    assert a["unplanned"]["by_reason"][0]["reason"] == "change_request"
    assert a["learning_impact"]["rows"][0]["final_ape"] is not None
    assert a["estimate_vs_actual"]["enough"] is False  # one project is not enough
    assert a["productivity"]["n"] == 1
    _delivered(db, other, "B1", 0.8)
    mine = analytics(db, [p1.id])
    assert all(r["name"] == "A1" for r in mine["estimate_vs_actual"]["rows"])
    assert analytics(db, [])["productivity"]["n"] == 0
