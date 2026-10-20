"""Guests can delete their own account and projects; nobody else can, and other people's data stays."""

from sqlalchemy import func, select

from app.db.models import Project, User
from tests.test_authz import _client, _h, _project_with_estimate, _user


def test_guest_can_delete_own_account_and_projects_only(db):
    admin = _user(db, "boss@example.com", role="admin")
    _user(db, "g1@guest.calibr", name="CALIBR-RUN-1 guest")
    _user(db, "g2@guest.calibr", name="CALIBR-RUN-2 guest")
    ca, c1, c2 = _client("boss@example.com"), _client("g1@guest.calibr"), _client("g2@guest.calibr")
    _project_with_estimate(ca, "admin project")
    pid, eid = _project_with_estimate(c1, "CALIBR-RUN-1 project")
    _project_with_estimate(c2, "CALIBR-RUN-2 project")
    s = c1.post(f"/api/v1/estimates/{eid}/agent/sessions", json={}, headers=_h(c1)).json()
    c1.post(f"/api/v1/agent/sessions/{s['id']}/runs", json={"text": "/similar"}, headers=_h(c1))

    assert c1.delete("/api/v1/auth/me", headers=_h(c1)).status_code == 204
    db.expire_all()
    assert db.scalar(select(User).where(User.email == "g1@guest.calibr")) is None
    assert db.scalar(select(func.count()).select_from(Project).where(Project.name == "CALIBR-RUN-1 project")) == 0
    assert db.scalar(select(func.count()).select_from(Project).where(Project.name == "CALIBR-RUN-2 project")) == 1
    assert db.scalar(select(func.count()).select_from(Project).where(Project.owner_id == admin.id)) == 1
    assert c1.get("/api/v1/auth/me").status_code == 401

    assert ca.delete("/api/v1/auth/me", headers=_h(ca)).status_code == 403  # admins are never deletable
    assert db.scalar(select(User).where(User.email == "boss@example.com")) is not None


def test_password_member_cannot_delete_account(db):
    _user(db, "real@example.com")
    c = _client("real@example.com")
    assert c.delete("/api/v1/auth/me", headers=_h(c)).status_code == 403
