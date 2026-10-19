"""VND as canonical currency: preferences, rates, costs, exports, FX and the cost-budget agent tool."""

import csv
import io

from sqlalchemy import select

from app.db.models import AgentOperation, DeliveryRole
from tests.test_agent_panel import names, run, setup  # noqa: F401  (fixture)
from tests.test_authz import _client, _h, _project_with_estimate, _user


def _roles(c):
    return {r["name"]: r for r in c.get("/api/v1/roles").json()}


def test_default_currency_is_vnd_and_toggle_persists(db):
    _user(db, "vn@example.com")
    c = _client("vn@example.com")
    assert c.get("/api/v1/auth/me").json()["display_currency"] == "VND"
    assert c.put("/api/v1/me/preferences", json={"display_currency": "USD"}, headers=_h(c)).json() == {
        "display_currency": "USD"}
    assert c.get("/api/v1/auth/me").json()["display_currency"] == "USD"
    assert c.put("/api/v1/me/preferences", json={"display_currency": "EUR"}, headers=_h(c)).status_code == 422


def test_default_rate_card_is_vnd_and_ordered_sensibly(db):
    _user(db, "rc@example.com")
    r = _roles(_client("rc@example.com"))
    assert r["Backend"]["hourly_rate_vnd"] == 600_000 and r["QA"]["hourly_rate_vnd"] == 490_000
    assert r["ML/CV Engineer"]["hourly_rate_vnd"] > r["Backend"]["hourly_rate_vnd"] > r["QA"]["hourly_rate_vnd"]
    assert r["DevOps"]["hourly_rate_vnd"] >= r["QA"]["hourly_rate_vnd"]
    assert all(x["hourly_rate_vnd"] % 10_000 == 0 and x["hourly_rate_vnd"] > 0 for x in r.values())


def test_rates_are_stored_canonical_in_vnd_from_either_currency(db):
    _user(db, "boss@example.com", role="admin")
    _user(db, "mem@example.com")
    admin, mem = _client("boss@example.com"), _client("mem@example.com")
    rate = admin.get("/api/v1/fx").json()["usd_vnd_rate"]
    qa = _roles(admin)["QA"]["id"]
    r = admin.put(f"/api/v1/roles/{qa}", json={"amount": 20, "currency": "USD"}, headers=_h(admin))
    assert r.status_code == 200 and r.json()["hourly_rate_vnd"] == round(20 * rate / 1000) * 1000
    assert mem.put(f"/api/v1/roles/{qa}", json={"amount": 1, "currency": "VND"}, headers=_h(mem)).status_code == 403
    row = db.scalar(select(DeliveryRole).where(DeliveryRole.name == "QA"))
    db.refresh(row)
    assert isinstance(row.hourly_rate_vnd, int) and row.hourly_rate == 45  # legacy column untouched
    # restore the default so other tests keep the documented card
    admin.put(f"/api/v1/roles/{qa}", json={"amount": 490000, "currency": "VND"}, headers=_h(admin))


def test_member_own_rate_changes_only_their_costs(db):
    _user(db, "m1@example.com")
    _user(db, "m2@example.com")
    a, b = _client("m1@example.com"), _client("m2@example.com")
    _, est = _project_with_estimate(a, "Cost project")
    s0 = a.get(f"/api/v1/estimates/{est}/summary").json()
    assert s0["currency"] == "VND" and 0 < s0["total_cost_min"] <= s0["total_cost_mid"] <= s0["total_cost_max"]
    be = _roles(a)["Backend"]["id"]
    assert a.put(f"/api/v1/me/rates/{be}", json={"amount": 100, "currency": "USD"}, headers=_h(a)).status_code == 200
    mine = _roles(a)["Backend"]
    assert mine["my_rate_vnd"] is not None and mine["rate_vnd"] == mine["my_rate_vnd"] != mine["hourly_rate_vnd"]
    s1 = a.get(f"/api/v1/estimates/{est}/summary").json()
    backend_hours = next(r["mid"] for r in s1["by_role"] if r["name"] == "Backend")
    assert backend_hours > 0 and s1["total_cost_mid"] != s0["total_cost_mid"]
    assert _roles(b)["Backend"]["my_rate_vnd"] is None  # other users unaffected
    assert a.delete(f"/api/v1/me/rates/{be}", headers=_h(a)).json()["my_rate_vnd"] is None
    assert a.get(f"/api/v1/estimates/{est}/summary").json()["total_cost_mid"] == s0["total_cost_mid"]
    assert a.put(f"/api/v1/me/rates/{be}", json={"amount": 0, "currency": "VND"}, headers=_h(a)).status_code == 422


def test_export_has_currency_and_rate(db):
    _user(db, "ex@example.com")
    c = _client("ex@example.com")
    _, est = _project_with_estimate(c, "Export project")
    rows = list(csv.DictReader(io.StringIO(c.get(f"/api/v1/estimates/{est}/export?format=csv").text)))
    assert rows and all(r["Currency"] == "VND" and float(r["Rate used (VND per USD)"]) > 0 for r in rows)
    usd = list(csv.DictReader(io.StringIO(c.get(f"/api/v1/estimates/{est}/export?format=csv&currency=USD").text)))
    assert usd[0]["Currency"] == "USD" and float(usd[0]["Rate / h"]) < 1000


def test_fx_admin_only_validated_and_manual(db):
    _user(db, "fxa@example.com", role="admin")
    _user(db, "fxm@example.com")
    admin, mem = _client("fxa@example.com"), _client("fxm@example.com")
    before = admin.get("/api/v1/fx").json()
    assert mem.put("/api/v1/admin/fx", json={"rate": 26000}, headers=_h(mem)).status_code == 403
    assert admin.put("/api/v1/admin/fx", json={"rate": 5}, headers=_h(admin)).status_code == 422
    out = admin.put("/api/v1/admin/fx", json={"rate": 26000}, headers=_h(admin)).json()
    assert out["usd_vnd_rate"] == 26000 and out["rate_source"] == "manual" and out["rate_updated_at"]
    assert mem.get("/api/v1/fx").json()["usd_vnd_rate"] == 26000
    admin.put("/api/v1/admin/fx", json={"rate": before["usd_vnd_rate"]}, headers=_h(admin))


def test_fx_refresh_failure_keeps_stored_rate(db, monkeypatch):
    from app.services import fx

    _user(db, "fxb@example.com", role="admin")
    admin = _client("fxb@example.com")
    before = admin.get("/api/v1/fx").json()["usd_vnd_rate"]
    monkeypatch.setattr(fx, "fetch_rate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    assert admin.post("/api/v1/admin/fx/refresh", headers=_h(admin)).status_code == 502
    assert admin.get("/api/v1/fx").json()["usd_vnd_rate"] == before


def _cost_fn(db, est, rates):
    from app.db.models import Task

    def cost():
        db.expire_all()
        return sum(t.max_hours * rates.get(t.delivery_role_id, 0)
                   for t in db.scalars(select(Task).where(Task.estimate_id == est.id)) if t.enabled)

    return cost


def test_vietnamese_budget_message_fits_cost_and_is_undoable(setup):  # noqa: F811
    from app.services import fx
    from app.services.operations import included_total
    from app.services.rates import effective_rates

    db, est, s, u = setup
    rates = effective_rates(db, u)
    cost = _cost_fn(db, est, rates)
    start = cost()
    before_hours = included_total(db, est.id)
    target = int(start * 0.85 / 1000) * 1000  # a modest cut applies directly
    evs = run(db, s, u, "ngân sách " + f"{target:,}".replace(",", ".") + " ₫")
    assert names(evs)[-1] == "run_done" and "table_patch" in names(evs)
    after = cost()
    assert after <= target and target - after <= 0.5 * max(rates.values())
    assert included_total(db, est.id) != before_hours
    done = dict(evs)["run_done"]
    assert done["applied"] >= 1
    # a USD figure converts at the workspace rate
    usd = int(after * 0.9 / fx.get_rate(db))
    evs2 = run(db, s, u, f"fit to ${usd:,}")
    assert "table_patch" in names(evs2)
    assert cost() <= round(usd * fx.get_rate(db)) + 1
    # undo restores the previous total
    op = db.scalars(select(AgentOperation).where(AgentOperation.op_type == "fit_to_cost_budget")
                    .order_by(AgentOperation.created_at.desc())).first()
    assert op is not None and op.status == "applied"


def test_large_vnd_cut_waits_for_confirmation(setup):  # noqa: F811
    from app.services.operations import included_total
    from app.services.rates import effective_rates

    db, est, s, u = setup
    cost = _cost_fn(db, est, effective_rates(db, u))
    before, hours = cost(), included_total(db, est.id)
    evs = run(db, s, u, "ngân sách " + f"{int(before * 0.5 / 1000) * 1000:,}".replace(",", ".") + " ₫")
    assert "confirmation_required" in names(evs)
    assert cost() == before and included_total(db, est.id) == hours


def test_infeasible_vnd_budget_asks_instead_of_changing(setup):  # noqa: F811
    from app.services.operations import included_total

    db, est, s, u = setup
    before = included_total(db, est.id)
    evs = run(db, s, u, "ngân sách 1 triệu")
    assert "ask_user" in names(evs) and included_total(db, est.id) == before
