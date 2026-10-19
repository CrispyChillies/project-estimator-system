import numpy as np
from sqlalchemy import select

from app.db.models import Project, RetrievalLog, TaskAIBaseline
from app.services import project_retrieval as pr
from app.services.documents import ingest
from app.services.generation import generate
from app.services.learning import finalize_estimate
from app.services.settings import LearningParams

BRIEFS = {
    "Shop A": (b"- Product catalog with search.\n- Shopping cart and Stripe checkout.\n- Admin panel for orders.\n",
               "ecommerce", ["react", "stripe"]),
    "Shop B": (b"- Product catalog.\n- Cart and checkout with Stripe payments.\n- Order admin dashboard.\n",
               "ecommerce", ["react", "stripe"]),
    "Clinic": (b"- Patient appointment booking.\n- Doctor calendar.\n- SMS reminders.\n", "health", ["django"]),
}


def _project(db, name, finalize=True):
    brief, domain, tags = BRIEFS[name]
    p = Project(name=name, status="delivered" if finalize else "draft", data_source="user", domain=domain,
                tech_tags=tags)
    db.add(p)
    db.commit()
    doc = ingest(db, p.id, "b.md", brief, None)
    est = generate(db, p.id, [doc.id], True, None)
    db.commit()
    if finalize:
        finalize_estimate(db, est.id, None, run_lessons=False)
        db.commit()
    return p, est


def test_retrieval_respects_eligible_ids_threshold_and_k(db):
    a, _ = _project(db, "Shop A")
    b, _ = _project(db, "Shop B")
    c, _ = _project(db, "Clinic")
    p = LearningParams(retrieval_min_similarity=0.0)
    n_logs = db.query(RetrievalLog).count()
    q = "Online shop: catalog, cart, Stripe checkout, admin orders"
    refs = pr.retrieve_projects(db, q, p, exclude_project_id=a.id, tags=["stripe"], domain="ecommerce")
    ids = [r.project_id for r in refs]
    assert str(a.id) not in ids and ids[0] == str(b.id) and len(ids) <= 3
    # leakage guard: only explicitly eligible projects can come back
    refs = pr.retrieve_projects(db, "patient booking with sms reminders", p, exclude_project_id=a.id,
                                eligible_project_ids=[c.id])
    assert [r.project_id for r in refs] == [str(c.id)]
    # never pad: a strict threshold returns fewer than k
    assert pr.retrieve_projects(db, q, LearningParams(retrieval_min_similarity=0.999), exclude_project_id=a.id) == []
    assert db.query(RetrievalLog).count() == n_logs + 3


def test_context_pack_respects_token_cap(db):
    a, _ = _project(db, "Shop A")
    refs = pr.retrieve_projects(db, "shop catalog cart", LearningParams(retrieval_min_similarity=0.0),
                                exclude_project_id=None)
    pack = pr.context_pack(refs[0], 200)
    assert pr.approx_tokens(pack) <= 260 and "Shop A" in pack


def test_generation_records_references(db):
    a, _ = _project(db, "Shop A")
    _project(db, "Clinic")
    new = Project(name="Shop C", status="draft", data_source="user", domain="ecommerce", tech_tags=["stripe"])
    db.add(new)
    db.commit()
    from app.services.settings import save_params

    save_params(db, {"retrieval_min_similarity": 0.0})
    doc = ingest(db, new.id, "b.md", BRIEFS["Shop B"][0], None)
    est = generate(db, new.id, [doc.id], True, None)
    db.commit()
    meta = est.model_snapshot["retrieval"]
    assert meta["variant"] == "ctx_k3" and meta["pack_hash"] and str(a.id) in meta["project_ids"]
    assert str(new.id) not in meta["project_ids"]
    b = db.scalars(select(TaskAIBaseline).where(TaskAIBaseline.estimate_id == est.id)).first()
    assert b.retrieval["project_ids"] == meta["project_ids"] and b.provenance["reference_projects"]


def test_generation_without_context(db):
    from app.services.settings import save_params

    save_params(db, {"retrieval_context_enabled": False})
    _, est = _project(db, "Shop A", finalize=False)
    assert est.model_snapshot["retrieval"]["variant"] == "noctx"


def test_mmr_prefers_diversity():
    vecs = np.array([[1, 0], [0.99, 0.01], [0.6, 0.8]], dtype=float)
    assert pr.mmr([0.9, 0.89, 0.8], vecs, 2, 0.7) == [0, 2]
    assert pr.mmr([0.9, 0.89, 0.8], vecs, 2, 1.0) == [0, 1]
