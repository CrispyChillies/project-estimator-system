from sqlalchemy import select

from app.db.models import Project, User
from app.llm.gateway import LLMGateway, use_gateway
from app.services.documents import ingest
from app.services.generation import generate
from app.services.learning import finalize_estimate, load_records, model_status, recompute

BRIEF = b"- Admin panel to manage users.\n- Integrate with the CRM to sync contacts.\n- Email notifications.\n"


def test_fake_and_live_histories_never_mix(db):
    p = Project(name="mk", status="draft", data_source="user")
    db.add(p)
    db.commit()
    doc = ingest(db, p.id, "b.md", BRIEF, None)
    u = db.scalar(select(User).where(User.email == "alice@calibr.local"))
    est = generate(db, p.id, [doc.id], False, u.id)
    finalize_estimate(db, est.id, u.id, run_lessons=False)
    db.commit()
    assert est.model_key == "fake-v1"
    assert len(load_records(db)) == 1
    status = model_status(db)
    assert status["active_model_key"] == "fake-v1" and not status["restarted"]

    live = LLMGateway(model="gpt-6-luna", mode="replay", reasoning="none")
    with use_gateway(live):
        assert load_records(db) == []  # fake history invisible to the live model_key
        recompute(db, "manual")
        db.commit()
        status = model_status(db)
        assert status["restarted"] and status["final_estimates_by_key"] == {"fake-v1": 1}
        assert status["calibration_model_key"] == live.model_key
