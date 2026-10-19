"""Live smoke test of the chat agent with the real model (budget-guarded, section cap $0.50).

Runs 6 scripted conversations on a fresh project (estimate generated with the offline LLM so only the chat costs
money), checks which tools were called and whether the estimate changed as expected, and prints a markdown table
with tool-call accuracy and cost per session.

  DATABASE_URL=...calibr_e2e LLM_MODE=live python scripts/live_chat_smoke.py
"""

import json
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agents.runtime import acquire_lock, stream_run  # noqa: E402
from app.db.models import AgentMessage, AgentSession, Estimate, LLMCall, Module, Project, Task, User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.llm import budget  # noqa: E402
from app.llm.gateway import LLMGateway, use_gateway  # noqa: E402
from app.services.documents import ingest  # noqa: E402
from app.services.generation import generate  # noqa: E402
from app.services.operations import included_total  # noqa: E402

BRIEF = b"""Courier dispatch platform for a regional logistics company.
- Customer web portal to book deliveries and track them live on a map.
- Back office for dispatchers to assign couriers and manage pricing rules.
- Courier mobile app with route list and proof of delivery photos.
- Payments with Stripe and monthly invoicing for business customers.
- Push and email notifications for status changes.
- Admin reporting dashboard with KPIs.
"""


def _events(stream) -> list[tuple[str, dict]]:
    out = []
    for chunk in stream:
        ev, data = chunk.split("\n", 1)
        out.append((ev.removeprefix("event: "), json.loads(data.removeprefix("data: ").strip())))
    return out


def main() -> int:
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.role == "admin", User.archived.is_(False)))
        with use_gateway(LLMGateway(mode="fake")):
            p = Project(name=f"Live chat smoke {uuid.uuid4().hex[:6]}", status="draft", data_source="user",
                        owner_id=admin.id)
            db.add(p)
            db.commit()
            doc = ingest(db, p.id, "brief.md", BRIEF, admin.id)
            est = generate(db, p.id, [doc.id], True, admin.id)
            db.commit()
        groups = [m.name for m in db.scalars(select(Module).where(Module.estimate_id == est.id))]
        big = max(db.scalars(select(Task).where(Task.estimate_id == est.id)), key=lambda t: t.max_hours)
        auth_group = next((g for g in groups if "auth" in g.lower() or "account" in g.lower()), groups[0])
        total0 = included_total(db, est.id)

    scripts = [
        ("fit-to-budget", "Fit the whole estimate to 400 hours", lambda tools, d: "fit_to_budget" in tools),
        ("add task", f"Add an SSO task under {auth_group} with 12-20 hours", lambda tools, d: "create_task" in tools
         and d["sso"]),
        ("bulk adjust", "Reduce QA by 20%", lambda tools, d: "bulk_adjust" in tools or "rebalance_roles" in tools),
        ("explain", f"Why is the {big.title} task so high?", lambda tools, d: "explain_task" in tools
         and not d["changed"]),
        ("ambiguous", "Make it cheaper", lambda tools, d: "ask_user" in tools or (d["changed"] and d["explained"])),
        ("nonexistent target", "Add a task for invoice exports under the Billing Reports group with 6-10 hours",
         lambda tools, d: not d["created_in_missing_group"]),
    ]
    rows = []
    with budget.budget("chat-smoke", 0.50):
        for name, text, check in scripts:
            with SessionLocal() as db:
                s = AgentSession(estimate_id=est.id, mode="chat", created_by=admin.id, state={}, title=name)
                db.add(s)
                db.commit()
                sid = s.id
                before = included_total(db, est.id)
                spend0 = db.scalar(select(LLMCall.id).order_by(LLMCall.created_at.desc()).limit(1))
                del spend0
                acquire_lock(db, sid)
            evs = _events(stream_run(sid, text, admin.id))
            with SessionLocal() as db:
                s = db.get(AgentSession, sid)
                msg = db.scalar(select(AgentMessage).where(AgentMessage.session_id == sid,
                                                           AgentMessage.role == "assistant"))
                tools = [c["name"] for c in (msg.tool_calls if msg else [])]
                after = included_total(db, est.id)
                sso = db.scalar(select(Task).where(Task.estimate_id == est.id, Task.title.ilike("%sso%"),
                                                   Task.removed.is_(False))) is not None
                missing = db.scalar(select(Module).where(Module.estimate_id == est.id,
                                                         Module.name.ilike("%billing report%")))
                facts = {"changed": after != before, "sso": sso, "explained": bool(msg and len(msg.content) > 40),
                         "created_in_missing_group": missing is not None and any(
                             t.module_id == missing.id for t in db.scalars(select(Task).where(
                                 Task.estimate_id == est.id)))}
                status = next((d.get("status") for e, d in evs if e == "run_done"), "?")
                errors = [d.get("message") for e, d in evs if e == "error"]
                rows.append({"name": name, "prompt": text, "tools": tools, "status": status, "ok": check(tools, facts),
                             "cost_usd": round(s.cost_usd, 5), "tokens": s.tokens, "errors": errors,
                             "reply": (msg.content if msg else "")[:160].replace("\n", " ")})
    with SessionLocal() as db:
        e = db.get(Estimate, est.id)
        del e
    print(json.dumps({"total_before": total0, "rows": rows}, indent=1))
    print("\n| # | scenario | tools called | run status | pass | cost USD | tokens |\n|---|---|---|---|---|---:|---:|")
    for i, r in enumerate(rows, 1):
        print(f"| {i} | {r['name']} | {', '.join(r['tools']) or '—'} | {r['status']} | {'yes' if r['ok'] else 'NO'} "
              f"| {r['cost_usd']:.4f} | {r['tokens']} |")
    acc = sum(r["ok"] for r in rows) / len(rows)
    print(f"\nTool-call accuracy: {acc:.0%} ({sum(r['ok'] for r in rows)}/{len(rows)}); "
          f"total cost ${sum(r['cost_usd'] for r in rows):.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
