import json
import uuid

import pytest
from sqlalchemy import select

from app.agents import memory
from app.agents.runtime import acquire_lock, stream_run
from app.api import agent_panel as api
from app.core.errors import Conflict
from app.db.models import AgentMessage, AgentOperation, AgentSession, Module, Project, Task, User
from app.services import estimates as es
from app.services.operations import included_total


def _events(stream) -> list[tuple[str, dict]]:
    out = []
    for chunk in stream:
        ev, data = chunk.split("\n", 1)
        out.append((ev.removeprefix("event: "), json.loads(data.removeprefix("data: ").strip())))
    return out


@pytest.fixture
def setup(db):
    u = db.scalar(select(User).where(User.email == "alice@calibr.local"))
    p = Project(name="Agent demo", status="draft", data_source="user")
    db.add(p)
    db.commit()
    from app.db.models import Estimate

    est = Estimate(project_id=p.id, version=1, status="draft", source="manual")
    db.add(est)
    db.flush()
    sys = es.SYSTEM
    roles = {r.name: r.id for r in db.scalars(select(__import__("app.db.models", fromlist=["DeliveryRole"]).DeliveryRole))}
    auth = es.create_module(db, est.id, "Authentication", sys, log=False)
    p1 = es.create_module(db, est.id, "Phase 1", sys, log=False)
    core = es.create_module(db, est.id, "Core", sys, log=False)
    specs = [(auth, "Login and sessions", 8, 16, "Backend"), (auth, "Password reset", 4, 8, "Backend"),
             (p1, "Landing page", 10, 20, "Frontend"), (p1, "Marketing CMS", 12, 30, "Backend"),
             (core, "Booking API", 20, 40, "Backend"), (core, "Booking UI", 16, 36, "Frontend"),
             (core, "QA regression", 10, 22, "QA"), (core, "Admin dashboard", 14, 28, "Frontend")]
    for m, title, lo, hi, role in specs:
        es.create_task(db, est.id, {"module_id": m.id, "title": title, "min_hours": lo, "max_hours": hi,
                                    "delivery_role_id": roles.get(role)}, sys, origin="ai", log=False)
    s = AgentSession(estimate_id=est.id, mode="chat", created_by=u.id, state={})
    db.add(s)
    db.commit()
    return db, est, s, u


def run(db, s, u, text, key=None):
    acquire_lock(db, s.id)
    evs = _events(stream_run(s.id, text, u.id, key))
    db.expire_all()
    return evs


def names(evs):
    return [e for e, _ in evs]


def test_fit_to_budget_auto_applies_and_streams_patch(setup):
    db, est, s, u = setup
    evs = run(db, s, u, "Fit the whole estimate to 180 hours")
    assert names(evs)[0] == "run_started" and names(evs)[-1] == "run_done"
    assert "tool_call_started" in names(evs) and "table_patch" in names(evs)
    assert included_total(db, est.id)[1] == 180
    done = dict(evs)["run_done"]
    assert done["status"] == "completed" and done["applied"] == 1
    msg = db.scalar(select(AgentMessage).where(AgentMessage.session_id == s.id, AgentMessage.role == "assistant"))
    assert msg.tool_calls[0]["name"] == "fit_to_budget" and "180" in msg.content


def test_large_change_needs_confirmation_then_confirm_and_undo(setup):
    db, est, s, u = setup
    before = included_total(db, est.id)
    evs = run(db, s, u, "/fit 100")
    conf = dict(evs)["confirmation_required"]
    assert dict(evs)["run_done"]["status"] == "awaiting_confirmation"
    assert included_total(db, est.id) == before  # nothing applied yet
    out = api.confirm_op(uuid.UUID(conf["operation_id"]), db, u.id)
    assert out["status"] == "applied" and included_total(db, est.id)[1] == 100
    api.undo_op(uuid.UUID(conf["operation_id"]), db, u.id)
    db.expire_all()
    assert included_total(db, est.id) == before
    roles = [m.role for m in db.scalars(select(AgentMessage).where(AgentMessage.session_id == s.id)
                                        .order_by(AgentMessage.created_at))]
    assert roles.count("system_event") == 2


def test_infeasible_budget_asks_user(setup):
    db, est, s, u = setup
    before = included_total(db, est.id)
    evs = run(db, s, u, "fit to 20 hours")
    ask = dict(evs)["ask_user"]
    assert "Cannot fit" in ask["question"] and ask["options"]
    assert dict(evs)["run_done"]["status"] == "awaiting_user"
    assert included_total(db, est.id) == before


def test_rebalance_hide_round_tighten(setup):
    db, est, s, u = setup
    run(db, s, u, "Make backend about 40% of the total")
    t = db.scalars(select(Task).where(Task.estimate_id == est.id)).all()
    be = [x for x in t if x.title in ("Login and sessions", "Password reset", "Marketing CMS", "Booking API")]
    share = sum((x.min_hours + x.max_hours) / 2 for x in be) / sum((x.min_hours + x.max_hours) / 2 for x in t)
    assert abs(share - 0.40) < 0.03
    evs = run(db, s, u, "Hide Phase 1")
    assert "table_patch" in names(evs)
    p1 = db.scalar(select(Module).where(Module.estimate_id == est.id, Module.name == "Phase 1"))
    assert all(not x.enabled for x in db.scalars(select(Task).where(Task.module_id == p1.id)))
    run(db, s, u, "Round everything to half hours")
    assert all((x.max_hours * 2).is_integer() for x in db.scalars(select(Task).where(Task.estimate_id == est.id)))
    widths = sorted((x.max_hours - x.min_hours for x in db.scalars(select(Task).where(
        Task.estimate_id == est.id, Task.enabled))), reverse=True)
    run(db, s, u, "Tighten the 3 widest ranges")
    after = sorted((x.max_hours - x.min_hours for x in db.scalars(select(Task).where(
        Task.estimate_id == est.id, Task.enabled))), reverse=True)
    assert after[0] < widths[0]


def test_add_task_under_existing_and_missing_group(setup):
    db, est, s, u = setup
    run(db, s, u, "Add an SSO task under Authentication with 12–20 hours")
    t = db.scalar(select(Task).where(Task.estimate_id == est.id, Task.title == "SSO"))
    assert t and (t.min_hours, t.max_hours) == (12, 20) and t.origin == "agent"
    n = db.query(Task).count()
    evs = run(db, s, u, "Add an SSO task under Billing with 12–20 hours")
    res = [d for e, d in evs if e == "tool_call_result"][0]
    assert not res["ok"] and res["error"] == "group_not_found" and "Authentication" in res["message"]
    assert db.query(Task).count() == n


def test_delete_always_confirms_and_review_mode(setup):
    db, est, s, u = setup
    evs = run(db, s, u, "delete the Password reset task")
    assert dict(evs)["confirmation_required"]["reasons"][0].startswith("Deletes")
    s2 = db.get(AgentSession, s.id)
    s2.apply_mode = "review"
    db.commit()
    evs = run(db, s, u, "/adjust +5%")
    assert "Review mode" in dict(evs)["confirmation_required"]["reasons"][0]


def test_vague_request_asks(setup):
    db, est, s, u = setup
    evs = run(db, s, u, "make it better")
    assert "ask_user" in names(evs) and "table_patch" not in names(evs)


def test_idempotency_and_lock(setup):
    db, est, s, u = setup
    run(db, s, u, "/adjust +10% backend", key="k1")
    total = included_total(db, est.id)
    evs = run(db, s, u, "/adjust +10% backend", key="k1")
    assert dict(evs)["run_done"]["status"] == "duplicate" and included_total(db, est.id) == total
    acquire_lock(db, s.id)
    with pytest.raises(Conflict):
        acquire_lock(db, s.id)


def test_remember_budget_binds_fit(setup):
    db, est, s, u = setup
    evs = run(db, s, u, "set a budget of 170")
    assert "memory_updated" in names(evs)
    assert db.get(AgentSession, s.id).state["budget_hours"] == 170
    run(db, s, u, "/fit")  # no number -> help; the planner requires a number for /fit
    from app.agents.toolkit import RunContext, Toolkit

    kit = Toolkit(RunContext(db, db.get(AgentSession, s.id), u.id, uuid.uuid4()))
    res = kit.call("fit_to_budget", {})
    assert res["ok"] and res["status"] == "applied"
    assert included_total(db, est.id)[1] == 170


def test_batch_undo_and_partial(setup):
    db, est, s, u = setup
    before = included_total(db, est.id)
    evs = run(db, s, u, "/adjust +10%")
    batch = dict(evs)["run_done"]["batch_id"]
    t = db.scalar(select(Task).where(Task.estimate_id == est.id, Task.title == "Booking API"))
    es.update_task(db, t.id, {"max_hours": 99}, es.Actor("user", u.id))
    db.commit()
    res = api.undo_batch(uuid.UUID(batch), db, u.id)
    assert res["results"][0]["partial"] and res["results"][0]["skipped"][0]["title"] == "Booking API"
    assert included_total(db, est.id) != before
    op = db.scalar(select(AgentOperation).where(AgentOperation.batch_id == uuid.UUID(batch)))
    assert op.status == "reverted"


def test_rolling_summary(setup, monkeypatch):
    db, est, s, u = setup
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "agent_history_token_budget", 50)
    for i in range(6):
        db.add(AgentMessage(session_id=s.id, role="user" if i % 2 == 0 else "assistant", content=f"turn {i} " * 20))
        db.commit()
    assert memory.roll_summary(db, s)
    assert "turn 0" in s.summary and s.summary_upto_message_id is not None
    assert len(memory.history_messages(db, s, exclude_last=False)) < 6
    assert "Session settings" in memory.system_prompt(db, s)


def test_live_path_with_scripted_model(setup):
    """Same toolkit and events through the LangChain agent loop (model scripted, no network)."""
    from langchain_core.messages import AIMessage

    from app.agents.cassettes import ReplayChatModel

    db, est, s, u = setup
    script = iter([
        AIMessage(content="", tool_calls=[{"name": "fit_to_budget", "args": {"target_hours": 180}, "id": "c1",
                                           "type": "tool_call"}]),
        AIMessage(content="", tool_calls=[{"name": "delete_tasks", "args": {"tasks": ["Password reset"]},
                                           "id": "c2", "type": "tool_call"}]),
        AIMessage(content="Fitted to 180 h; the delete is waiting for your confirmation."),
    ])
    acquire_lock(db, s.id)
    evs = _events(stream_run(s.id, "fit to 180 and drop password reset", u.id,
                             model=ReplayChatModel(messages=script, disable_streaming=True)))
    db.expire_all()
    n = names(evs)
    assert n.count("tool_call_started") == 2 and "table_patch" in n and "confirmation_required" in n
    assert dict(evs)["run_done"]["status"] == "awaiting_confirmation"
    assert included_total(db, est.id)[1] == 180
    assert "confirmation" in dict(evs)["message_done"]["text"]
