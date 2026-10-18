"""Model bake-off: Extraction -> Decomposition -> K=3 Estimation on 3 synthetic briefs + 8 scripted agent commands.

  python scripts/bakeoff.py --dry-run            # planned calls + estimated cost; refuses if over budget
  LLM_MODE=record python scripts/bakeoff.py      # runs, caches structured outputs under each model_key
Results are written to data/fixtures/bakeoff_results.json (synthetic inputs only).
"""

import argparse
import json
import statistics
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.agents import chains  # noqa: E402
from app.agents.chat_agent import stream_agent  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.datasets.synthetic import generate as synth  # noqa: E402
from app.db.models import AgentMessage, EditEvent, LLMCall, Module, Project, Task  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.llm import budget  # noqa: E402
from app.llm.gateway import LLMGateway, use_gateway  # noqa: E402
from app.services.documents import ingest  # noqa: E402
from app.services.generation import generate  # noqa: E402

MODELS = [("A", "gpt-6-luna", "none"), ("B", "gpt-6.1-sol", "low")]
SECTION_LIMIT = 1.50
AMBIGUOUS_SUFFIX = """
## Open points from the kick-off call (contradictory notes)
- Payments are not needed in phase 1. Customers must pay by card at checkout though.
- Maybe SSO with the client's Azure AD? Not sure yet.
- The mobile app might be native or a PWA, TBD.
- Admin users should see all data; regional managers must not see other regions (or maybe they should?).
- Launch in 6 weeks; full feature set required for launch.
"""
AGENT_COMMANDS = [
    ("increase backend hours by 20%", {"propose_bulk_adjust"}),
    ("add an SSO task under Authentication", {"propose_add_task"}),
    ("remove the admin dashboard module", {"propose_remove_module", "propose_remove_task"}),
    ("split the payments task into two", {"propose_split_task"}),
    ("why is the integration task so high?", {"explain_task"}),
    ("find similar past tasks for the reporting module", {"find_similar_past_tasks"}),
    ("set QA tasks to at least 8 hours", {"propose_update_task", "propose_bulk_adjust"}),
    ("make it cheaper", set()),  # correct: clarify, or one bounded explained change
]


def briefs() -> list[dict]:
    projects = sorted(synth(), key=lambda p: len(p.tasks))
    small, medium, large = projects[0], projects[len(projects) // 2], projects[-1]
    out = []
    for label, p, extra in [("small+ambiguous", small, AMBIGUOUS_SUFFIX), ("medium", medium, ""), ("large", large, "")]:
        actual = sum(t.actual or 0 for t in p.tasks)
        out.append({"label": label, "name": p.name, "text": p.brief + extra, "actual_planned": actual,
                    "n_seeded_tasks": len(p.tasks)})
    return out


def dry_run_estimate(bs: list[dict]) -> dict:
    """Character-based token estimate (≈4 chars/token) with conservative output assumptions."""
    k = get_settings().raw_samples
    plan = {}
    for _label, model, reasoning in MODELS:
        p = budget.prices()[model]
        extra_out = 600 if reasoning not in ("none", "") else 0  # hidden reasoning tokens
        cost, calls = 0.0, 0
        for b in bs:
            tin = budget.estimate_tokens(b["text"]) + 700
            stages = [(tin, 2500), (1800, 3500)] + [(2000, 1200)] * k
            for i, o in stages:
                cost += (i * p["input"] + (o + extra_out) * p["output"]) / 1e6
                calls += 1
        for _ in AGENT_COMMANDS:  # ~4 model turns per command, growing context
            cost += 4 * (4000 * p["input"] + (300 + extra_out) * p["output"]) / 1e6
            calls += 4
        plan[model] = {"calls": calls, "est_cost_usd": round(cost * 1.3, 4)}  # +30% safety margin
    plan["total_est_cost_usd"] = round(sum(v["est_cost_usd"] for v in plan.values() if isinstance(v, dict)), 4)
    plan["section_limit_usd"] = SECTION_LIMIT
    return plan


def tool_calls_since(db, session_id) -> list[dict]:
    calls = []
    for m in db.scalars(select(AgentMessage).where(AgentMessage.session_id == session_id, AgentMessage.role == "assistant")):
        calls += m.tool_calls or []
    return calls


def agent_eval(db, estimate_id) -> dict:
    before = {(t.id, t.min_hours, t.max_hours, t.removed, t.enabled) for t in db.scalars(select(Task).where(Task.estimate_id == estimate_id))}
    rows = []
    for text, expected in AGENT_COMMANDS:
        t0 = time.monotonic()
        events = list(stream_agent(db, estimate_id, None, text, None))
        sid = json.loads(events[0].split("data: ", 1)[1])["session_id"]
        calls = tool_calls_since(db, uuid.UUID(sid))
        names = [c["name"] for c in calls]
        bad = [c for c in calls if str(c.get("result", "")).startswith(("Tool error", "Task not found", "No tasks match",
                                                                           "No module matches"))]
        proposals = [n for n in names if n.startswith("propose_")]
        reply = "".join(json.loads(e.split("data: ", 1)[1]).get("text", "") for e in events if e.startswith("event: token"))
        if expected:
            correct = bool(expected & set(names))
        else:  # vague request: no proposal (clarify) or exactly one bounded op
            correct = len(proposals) <= 1
        rows.append({"command": text, "tools": names, "correct": correct, "malformed_args": len(bad),
                     "errors": [e for e in events if e.startswith("event: error")][:1], "reply": reply[:300],
                     "seconds": round(time.monotonic() - t0, 1)})
    after = {(t.id, t.min_hours, t.max_hours, t.removed, t.enabled) for t in db.scalars(select(Task).where(Task.estimate_id == estimate_id))}
    mutated = before != after or db.scalar(select(EditEvent.id).where(EditEvent.estimate_id == estimate_id)) is not None
    return {"commands": rows, "correct": sum(r["correct"] for r in rows), "total": len(rows),
            "malformed": sum(r["malformed_args"] for r in rows), "estimate_mutated_without_accept": mutated}


def coverage(db, estimate_id) -> dict:
    tasks = list(db.scalars(select(Task).where(Task.estimate_id == estimate_id)))
    titles = " | ".join(t.title.lower() for t in tasks)
    hidden = {"ci_cd": any(k in titles for k in ("ci/cd", "pipeline", "deploy")),
              "qa": any(k in titles for k in ("qa", "test")), "review": "review" in titles,
              "pm": any(k in titles for k in ("project management", "pm ", "communication", "coordination"))}
    n_mod = len(list(db.scalars(select(Module).where(Module.estimate_id == estimate_id))))
    return {"tasks": len(tasks), "modules": n_mod, "hidden_tasks": hidden}


def run_model(label: str, model: str, reasoning: str, bs: list[dict]) -> dict:
    gw = LLMGateway(model=model, mode=get_settings().llm_mode, reasoning=reasoning)
    res = {"label": label, "model": model, "reasoning": reasoning, "model_key": gw.model_key, "briefs": []}
    t_start = time.time()
    with use_gateway(gw), SessionLocal() as db:
        medium_estimate = None
        for b in bs:
            chains.EXTRACTION_STATS.clear()
            p = Project(name=f"bakeoff {model} {b['label']}", status="draft", data_source="synthetic",
                        description="model bake-off (synthetic brief)")
            db.add(p)
            db.commit()
            doc = ingest(db, p.id, f"{b['label']}.md", b["text"].encode(), None)
            t0 = time.monotonic()
            try:
                est = generate(db, p.id, [doc.id], False, None)
                db.commit()
            except budget.BudgetExceeded:
                raise
            except Exception as e:
                db.rollback()
                res["briefs"].append({"brief": b["label"], "error": getattr(e, "message", str(e))[:300]})
                continue
            raw = est.model_snapshot
            samples: dict[str, list] = {}
            from app.db.models import LLMRawEstimate
            for r in db.scalars(select(LLMRawEstimate).where(LLMRawEstimate.project_id == p.id)):
                samples.setdefault(r.task_key, []).append((r.raw_min + r.raw_max) / 2)
            cvs = [statistics.pstdev(v) / statistics.mean(v) for v in samples.values() if len(v) > 1 and statistics.mean(v) > 0]
            k = max((len(v) for v in samples.values()), default=0)
            totals = [sum(v[i] for v in samples.values() if len(v) > i) for i in range(k)]
            from app.db.models import Assumption, ClarifyingQuestion
            amb = db.scalars(select(Assumption).where(Assumption.estimate_id == est.id)).all()
            qs = db.scalars(select(ClarifyingQuestion).where(ClarifyingQuestion.estimate_id == est.id)).all()
            res["briefs"].append({
                "brief": b["label"], "seconds": round(time.monotonic() - t0, 1),
                "extraction": chains.EXTRACTION_STATS[0] if chains.EXTRACTION_STATS else None,
                **coverage(db, est.id), "unknowns": len(qs), "assumption_items": len(amb),
                "unknown_questions": [q.question for q in qs][:8],
                "median_task_cv": round(statistics.median(cvs), 3) if cvs else None,
                "total_spread": round((max(totals) - min(totals)) / statistics.mean(totals), 3) if totals else None,
                "total_mid": round(statistics.median(totals), 1) if totals else None,
                "actual_planned": round(b["actual_planned"], 1),
                "ratio_to_actual": round(statistics.median(totals) / b["actual_planned"], 2) if totals else None,
                "summary_hint": str(raw.get("summary", ""))[:200],
            })
            if b["label"] == "medium":
                medium_estimate = est.id
        if medium_estimate:
            res["agent"] = agent_eval(db, medium_estimate)
        # schema validity + latency + cost from llm_calls for this model in this run
        calls = list(db.scalars(select(LLMCall).where(LLMCall.model == model, LLMCall.cache_hit.is_(False))
                                .where(LLMCall.created_at >= time_from(t_start))))
        structured = [c for c in calls if c.purpose in ("extraction", "decomposition", "estimation")]
        invalid = [c for c in structured if isinstance(c.response, dict) and "error" in c.response]
        lat = sorted(c.latency_ms for c in calls)
        res["structured_calls"] = len(structured)
        res["schema_invalid"] = len(invalid)
        res["latency_ms_p50"] = lat[len(lat) // 2] if lat else None
        res["latency_ms_p95"] = lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else None
        res["cost_usd_generation"] = round(sum(c.cost_usd for c in structured) / max(len(bs), 1), 4)
        res["cost_usd_agent"] = round(sum(c.cost_usd for c in calls if c.purpose == "chat_agent"), 4)
        res["cost_usd_total"] = round(sum(c.cost_usd for c in calls), 4)
        res["reasoning_tokens"] = sum(c.reasoning_tokens for c in calls)
    return res


def time_from(ts: float):
    from datetime import UTC, datetime

    return datetime.fromtimestamp(ts, UTC)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", choices=["A", "B"])
    args = ap.parse_args()
    bs = briefs()
    plan = dry_run_estimate(bs)
    print(json.dumps({"briefs": [(b["label"], len(b["text"]), round(b["actual_planned"])) for b in bs], "plan": plan}, indent=1))
    if plan["total_est_cost_usd"] > SECTION_LIMIT:
        raise SystemExit(f"Refusing: estimated ${plan['total_est_cost_usd']} exceeds bake-off budget ${SECTION_LIMIT}")
    if args.dry_run:
        return
    out_path = get_settings().fixtures_dir / "bakeoff_results.json"
    results = json.loads(out_path.read_text()) if out_path.exists() else {}
    with budget.budget("bakeoff", SECTION_LIMIT):
        for label, model, reasoning in MODELS:
            if args.only and label != args.only:
                continue
            try:
                results[label] = run_model(label, model, reasoning, bs)
            except budget.BudgetExceeded as e:
                results[label] = {"label": label, "model": model, "aborted": e.message}
            out_path.write_text(json.dumps(results, indent=1, default=str))
            print(json.dumps({k: v for k, v in results[label].items() if k != "briefs"}, indent=1, default=str)[:3000])
    print(f"bake-off spend: ${budget.spend_fn():.4f} total so far; results -> {out_path}")


if __name__ == "__main__":
    main()
