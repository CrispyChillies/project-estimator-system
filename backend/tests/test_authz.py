"""Cross-user authorization, CSRF, sessions, sign-up rules, cost locks and learning-pool scoping."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.auth import hash_password
from app.db.models import LLMCall, Project, Task, User

PW = "correct horse battery"


def _user(db, email: str, role: str = "member", name: str | None = None) -> User:
    u = User(name=name or email.split("@")[0], email=email, role=role, password_hash=hash_password(PW),
             is_active=True, onboarding_state={})
    db.add(u)
    db.commit()
    return u


def _client(email: str) -> TestClient:
    from app.main import app

    c = TestClient(app)
    c.__enter__()
    c.get("/api/v1/auth/csrf")
    r = c.post("/api/v1/auth/login", json={"email": email, "password": PW}, headers=_h(c))
    assert r.status_code == 200, r.text
    return c


def _h(c: TestClient) -> dict:
    return {"X-CSRF-Token": c.cookies.get("calibr_csrf", "")}


def _project_with_estimate(c: TestClient, name: str) -> tuple[str, str]:
    p = c.post("/api/v1/projects", json={"name": name}, headers=_h(c)).json()
    c.post(f"/api/v1/projects/{p['id']}/documents/paste",
           json={"title": "brief", "text": "- Admin panel to manage users.\n- Email notifications.\n"},
           headers=_h(c)).raise_for_status()
    job = c.post(f"/api/v1/projects/{p['id']}/estimates/generate", json={"document_ids": [], "learning": True},
                 headers=_h(c)).json()
    j = c.get(f"/api/v1/jobs/{job['id']}").json()
    assert j["status"] == "done", j
    return p["id"], j["result_ref"]


@pytest.fixture
def two_members(db):
    _user(db, "a@example.com")
    _user(db, "b@example.com")
    return _client("a@example.com"), _client("b@example.com")


def test_unauthenticated_requests_get_401(db):
    from app.main import app

    with TestClient(app) as c:
        assert c.get("/api/v1/projects").status_code == 401
        assert c.get(f"/api/v1/estimates/{uuid.uuid4()}").status_code == 401
        assert c.get("/api/v1/health").status_code == 200
        assert c.get("/api/v1/auth/session").json() == {"user": None}


def test_session_status_reports_signed_in_user(db):
    _user(db, "s@example.com")
    c = _client("s@example.com")
    assert c.get("/api/v1/auth/session").json()["user"]["email"] == "s@example.com"
    c.post("/api/v1/auth/logout", headers=_h(c))
    assert c.get("/api/v1/auth/session").json() == {"user": None}


def test_member_cannot_touch_another_members_data(db, two_members):
    a, b = two_members
    pid, eid = _project_with_estimate(a, "A secret")
    tree = a.get(f"/api/v1/estimates/{eid}").json()
    tid = tree["modules"][0]["tasks"][0]["id"]
    mid = tree["modules"][0]["id"]
    doc = a.get(f"/api/v1/projects/{pid}/documents").json()[0]["id"]
    sess = a.post(f"/api/v1/estimates/{eid}/agent/sessions", json={}, headers=_h(a)).json()["id"]
    mem = a.post(f"/api/v1/estimates/{eid}/memories", json={"text": "client pays in EUR"}, headers=_h(a)).json()["id"]

    assert pid not in [p["id"] for p in b.get("/api/v1/projects").json()]
    for path in (f"/projects/{pid}", f"/projects/{pid}/documents", f"/documents/{doc}/chunks", f"/estimates/{eid}",
                 f"/estimates/{eid}/summary", f"/estimates/{eid}/activity", f"/estimates/{eid}/agent/sessions",
                 f"/agent/sessions/{sess}/messages", f"/agent/sessions/{sess}/operations",
                 f"/estimates/{eid}/memories", f"/projects/{pid}/actuals", f"/projects/{pid}/unplanned",
                 f"/estimates/{eid}/references", f"/projects/{pid}/members"):
        assert b.get(f"/api/v1{path}").status_code == 404, path
    h = _h(b)
    assert b.patch(f"/api/v1/tasks/{tid}", json={"max_hours": 1}, headers=h).status_code == 404
    assert b.patch(f"/api/v1/modules/{mid}", json={"name": "x"}, headers=h).status_code == 404
    assert b.delete(f"/api/v1/projects/{pid}", headers=h).status_code == 404
    assert b.post(f"/api/v1/agent/sessions/{sess}/runs", json={"text": "/round"}, headers=h).status_code == 404
    assert b.patch(f"/api/v1/memories/{mem}", json={"enabled": False}, headers=h).status_code == 404
    assert b.post(f"/api/v1/estimates/{eid}/finalize", headers=h).status_code == 404
    assert b.post("/api/v1/chunks/lookup", json=[str(uuid.uuid4())], headers=h).json() == []
    assert b.get("/api/v1/backtest/runs").json() == []
    assert b.get("/api/v1/rules").json() == []
    # Still intact for the owner
    assert a.get(f"/api/v1/tasks/{tid}" if False else f"/api/v1/estimates/{eid}").status_code == 200


def test_sharing_viewer_and_editor(db, two_members):
    a, b = two_members
    pid, eid = _project_with_estimate(a, "Shared")
    tid = a.get(f"/api/v1/estimates/{eid}").json()["modules"][0]["tasks"][0]["id"]
    r = a.post(f"/api/v1/projects/{pid}/members", json={"email": "b@example.com", "role": "viewer"}, headers=_h(a))
    assert r.status_code == 201
    assert b.get(f"/api/v1/estimates/{eid}").status_code == 200
    assert b.patch(f"/api/v1/tasks/{tid}", json={"max_hours": 99}, headers=_h(b)).status_code == 403
    assert b.post(f"/api/v1/projects/{pid}/members", json={"email": "a@example.com"}, headers=_h(b)).status_code == 403
    a.post(f"/api/v1/projects/{pid}/members", json={"email": "b@example.com", "role": "editor"}, headers=_h(a))
    assert b.patch(f"/api/v1/tasks/{tid}", json={"max_hours": 99}, headers=_h(b)).status_code == 200


def test_csrf_required_on_writes(db, two_members):
    a, _ = two_members
    r = a.post("/api/v1/projects", json={"name": "x"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r = a.post("/api/v1/projects", json={"name": "x"}, headers={"X-CSRF-Token": "forged"})
    assert r.status_code == 403


def test_deactivated_user_loses_access_and_admin_only(db, two_members):
    a, _ = two_members
    _user(db, "root@example.com", role="admin")
    admin = _client("root@example.com")
    assert a.get("/api/v1/admin/users").status_code == 403
    roles = admin.get("/api/v1/roles").json()
    assert a.put(f"/api/v1/roles/{roles[0]['id']}", json={"hourly_rate": 1, "currency": "EUR"},
                 headers=_h(a)).status_code == 403
    uid = db.scalar(select(User.id).where(User.email == "a@example.com"))
    assert admin.patch(f"/api/v1/admin/users/{uid}", json={"is_active": False}, headers=_h(admin)).status_code == 200
    assert a.get("/api/v1/projects").status_code == 401


def test_logout_and_password_change_revoke_sessions(db, two_members):
    a, _ = two_members
    other = _client("a@example.com")
    r = a.post("/api/v1/auth/password", json={"current_password": PW, "new_password": "another long secret"},
               headers=_h(a))
    assert r.status_code == 204
    assert other.get("/api/v1/projects").status_code == 401  # other sessions revoked
    assert a.get("/api/v1/projects").status_code == 200
    a.post("/api/v1/auth/logout", headers=_h(a))
    assert a.get("/api/v1/projects").status_code == 401


def test_login_throttle_and_generic_errors(db):
    from app.main import app

    _user(db, "t@example.com")
    with TestClient(app) as c:
        c.get("/api/v1/auth/csrf")
        msgs = set()
        for _ in range(5):
            r = c.post("/api/v1/auth/login", json={"email": "t@example.com", "password": "wrong password!"},
                       headers=_h(c))
            msgs.add(r.json()["error"]["message"])
        r = c.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong password!"},
                   headers=_h(c))
        msgs.add(r.json()["error"]["message"])
        assert msgs == {"Email or password is incorrect"}  # no user enumeration
        r = c.post("/api/v1/auth/login", json={"email": "t@example.com", "password": PW}, headers=_h(c))
        assert r.status_code == 429


def test_signup_modes(db, monkeypatch):
    from app.core.config import get_settings
    from app.main import app

    s = get_settings()
    with TestClient(app) as c:
        c.get("/api/v1/auth/csrf")
        body = {"name": "N", "email": "n@example.com", "password": "a sufficiently long one"}
        monkeypatch.setattr(s, "signup_mode", "closed")
        assert c.post("/api/v1/auth/signup", json=body, headers=_h(c)).status_code == 403
        monkeypatch.setattr(s, "signup_mode", "invite")
        monkeypatch.setattr(s, "invite_code", "letmein-123")
        assert c.post("/api/v1/auth/signup", json={**body, "invite_code": "nope"}, headers=_h(c)).status_code == 403
        assert c.post("/api/v1/auth/signup", json={**body, "password": "short"}, headers=_h(c)).status_code == 403
        r = c.post("/api/v1/auth/signup", json={**body, "invite_code": "letmein-123"}, headers=_h(c))
        assert r.status_code == 201 and r.json()["role"] == "member"
        assert c.get("/api/v1/projects").json() == []  # clean workspace
        c2 = TestClient(app)
        c2.get("/api/v1/auth/csrf")
        r = c2.post("/api/v1/auth/signup", json={**body, "password": "short", "invite_code": "letmein-123"},
                    headers=_h(c2))
        assert r.status_code == 422


def test_model_cannot_be_changed(db, two_members):
    a, _ = two_members
    pid = a.post("/api/v1/projects", json={"name": "m"}, headers=_h(a)).json()["id"]
    r = a.post(f"/api/v1/projects/{pid}/estimates/generate",
               json={"document_ids": [], "learning": True, "model": "premium-model"}, headers=_h(a))
    assert r.status_code == 400 and r.json()["error"]["code"] == "model_locked"
    assert a.put("/api/v1/admin/learning", json={"shrink_k": 2}, headers=_h(a)).status_code == 403
    assert a.get("/api/v1/llm/usage").status_code == 404  # removed for everyone
    assert "model" not in a.get("/api/v1/me/usage").json()


def test_production_refuses_fake_llm():
    from app.core.bootstrap import ConfigError, validate_config
    from app.core.config import Settings

    with pytest.raises(ConfigError, match="LLM_MODE must be 'live'"):
        validate_config(Settings(app_env="production", llm_mode="fake", session_secret="x" * 40,
                                 openai_api_key="k", openai_model="m", openai_embedding_model="e",
                                 invite_code="invite-code-1"))
    with pytest.raises(ConfigError, match="LLM_MODE must be 'live'"):
        validate_config(Settings(app_env="production", llm_mode="replay", session_secret="x" * 40,
                                 openai_api_key="k", openai_model="m", openai_embedding_model="e",
                                 invite_code="invite-code-1"))


def test_daily_user_cap_enforced(db):
    from app.core.usage import AllowanceExceeded, check_user_allowance, use_llm_user

    u = _user(db, "spender@example.com")
    db.add(LLMCall(purpose="x", model="m", prompt_hash="h", cost_usd=0.6, user_id=u.id))
    db.commit()
    with use_llm_user(u.id), pytest.raises(AllowanceExceeded):
        check_user_allowance()
    u.daily_usd_cap = 2.0
    db.commit()
    with use_llm_user(u.id):
        check_user_allowance()


def test_member_pool_excludes_archive_unless_enabled(db, two_members):
    """Admin archive data never calibrates or is retrieved for members unless the admin switch is on."""
    from app.core.access import pool_project_ids
    from app.services.documents import ingest
    from app.services.generation import generate
    from app.services.learning import finalize_estimate, load_stats
    from app.services.settings import save_params

    save_params(db, {"retrieval_min_similarity": 0.0})
    admin = _user(db, "root@example.com", role="admin")
    arch = Project(name="Archived shop", status="draft", data_source="synthetic", is_archive=True, owner_id=admin.id)
    db.add(arch)
    db.commit()
    doc = ingest(db, arch.id, "b.md", b"- Admin panel to manage users.\n- Email notifications.\n", None)
    est = generate(db, arch.id, [doc.id], True, admin.id)
    for t in db.scalars(select(Task).where(Task.estimate_id == est.id)):
        t.max_hours *= 3
    finalize_estimate(db, est.id, admin.id, run_lessons=False)
    db.commit()
    member = db.scalar(select(User).where(User.email == "a@example.com"))
    assert arch.id not in pool_project_ids(db, member.id)
    assert load_stats(db, pool_project_ids(db, member.id)) == ({}, {})
    a, _ = two_members
    _, eid = _project_with_estimate(a, "Member project")
    assert a.get(f"/api/v1/estimates/{eid}/references").json()["references"] == []
    sim = a.get(f"/api/v1/estimates/{eid}/similar-projects").json()["references"]
    assert all(r["project_id"] != str(arch.id) for r in sim)
    assert a.get("/api/v1/insights/calibration").json() == []
    assert a.get("/api/v1/insights/scope").json()["includes_reference_library"] is False

    from app.db.models import Setting

    db.add(Setting(key="workspace", value={"include_archive_for_all": True}))
    db.commit()
    assert arch.id in pool_project_ids(db, member.id)
    sim = a.get(f"/api/v1/estimates/{eid}/similar-projects").json()["references"]
    assert [r["project_id"] for r in sim] == [str(arch.id)]
    assert a.get("/api/v1/insights/scope").json()["includes_reference_library"] is True


def test_quick_signin_mode(db, monkeypatch):
    from app.core.config import get_settings
    from app.main import app

    with TestClient(app) as c:
        c.get("/api/v1/auth/csrf")
        assert c.post("/api/v1/auth/quick", json={"name": "Q"}, headers=_h(c)).status_code == 403
        monkeypatch.setattr(get_settings(), "auth_mode", "quick")
        r = c.post("/api/v1/auth/quick", json={"name": "Quinn", "email": "quinn@example.com"}, headers=_h(c))
        assert r.status_code == 200 and r.json()["role"] == "member"
        assert c.get("/api/v1/projects").status_code == 200
        c.post("/api/v1/auth/logout", headers=_h(c))
        again = c.post("/api/v1/auth/quick", json={"name": "Quinn", "email": "quinn@example.com"}, headers=_h(c))
        assert again.json()["id"] == r.json()["id"]
        assert c.post("/api/v1/auth/quick", json={"name": "Guest"}, headers=_h(c)).json()["email"].startswith("guest-")
    _user(db, "boss@example.com", role="admin")
    with TestClient(app) as c:
        c.get("/api/v1/auth/csrf")
        assert c.post("/api/v1/auth/quick", json={"name": "x", "email": "boss@example.com"}, headers=_h(c)).status_code == 403
