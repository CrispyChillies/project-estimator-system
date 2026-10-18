"""Populate data/fixtures/llm_cache with the live model (LLM_MODE=record), budget-capped.

Steps: (1) the idempotent demo seed — for synthetic projects only the raw-estimation step (K samples per
project, fixed task list) plus embeddings and one lessons call; (2) optionally full generations for the demo
briefs (learning off/on) in a temporary project that is deleted afterwards.

  python scripts/warm_cache.py --dry-run [--demo-briefs]
  LLM_MODE=record python scripts/warm_cache.py [--demo-briefs]
Afterwards LLM_MODE=replay serves the same calls with zero live calls.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.datasets import synthetic  # noqa: E402
from app.llm import budget  # noqa: E402
from app.prompts import render  # noqa: E402

BRIEFS = ["demo_brief.md", "demo_brief_2.md"]
SEED_LIMIT = 2.00


def estimate(demo_briefs: bool) -> dict:
    s = get_settings()
    p = budget.prices()[s.openai_model]
    e = budget.prices()[s.openai_embedding_model]
    k = s.raw_samples
    calls = cost = emb_tokens = 0.0
    for sp in synthetic.generate():
        ai = [t for t in sp.tasks if t.origin == "ai"]
        prompt = render("estimation", summary=sp.name, rules="none",
                        tasks="\n".join(f"{t.key} | {t.role} | {t.category} | {t.title} — {t.description}" for t in ai))
        tin, tout = budget.estimate_tokens(prompt) + 50, 45 * len(ai)
        calls += k
        cost += k * (tin * p["input"] + tout * p["output"]) / 1e6
        emb_tokens += sum(budget.estimate_tokens(f"{t.title}\n{t.description}") for t in sp.tasks)
        emb_tokens += budget.estimate_tokens(sp.brief)
    calls += 1  # lessons chain
    cost += (6000 * p["input"] + 1500 * p["output"]) / 1e6
    if demo_briefs:
        per_gen = (2500 * p["input"] + 3000 * p["output"]) + (2000 * p["input"] + 3500 * p["output"]) \
            + k * (2200 * p["input"] + 1200 * p["output"])
        calls += len(BRIEFS) * 2 * (2 + k)
        cost += len(BRIEFS) * 2 * per_gen / 1e6
    cost += emb_tokens * e["input"] / 1e6
    return {"model": s.openai_model, "planned_llm_calls": int(calls), "embedding_tokens": int(emb_tokens),
            "est_cost_usd": round(cost * 1.3, 4), "section_limit_usd": SEED_LIMIT,
            "note": "≈4 chars/token, +30% margin; cache hits cost $0"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--demo-briefs", action="store_true")
    args = ap.parse_args()
    plan = estimate(args.demo_briefs)
    print(json.dumps(plan, indent=1))
    if plan["est_cost_usd"] > SEED_LIMIT:
        raise SystemExit(f"Refusing: estimate ${plan['est_cost_usd']} exceeds seed budget ${SEED_LIMIT}")
    if args.dry_run:
        return
    s = get_settings()
    if s.llm_mode != "record":
        raise SystemExit("Run with LLM_MODE=record (make warm-cache does this).")
    from scripts.seed_demo import main as seed

    with budget.budget("seed", SEED_LIMIT):
        seed()
        if args.demo_briefs:
            from app.db.models import Project
            from app.db.session import SessionLocal
            from app.services.documents import ingest
            from app.services.generation import generate

            with SessionLocal() as db:
                for name in BRIEFS:
                    p = Project(name=f"warm-cache {name}", status="draft", data_source="synthetic")
                    db.add(p)
                    db.commit()
                    doc = ingest(db, p.id, name, (s.fixtures_dir / name).read_bytes(), None)
                    for learning in (False, True):
                        generate(db, p.id, [doc.id], learning, None)
                        db.commit()
                    db.delete(p)
                    db.commit()
        print(f"seed section spend: ${budget.section_spent():.4f}")
    print(f"cache written to {s.fixtures_dir / 'llm_cache'}")


if __name__ == "__main__":
    main()
