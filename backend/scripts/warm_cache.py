"""Populate data/fixtures/llm_cache by running the live LLM once (LLM_MODE=record, OPENAI_API_KEY required).

Generates estimates (learning off and on) for the demo briefs in a temporary project, then deletes it.
Afterwards LLM_MODE=replay serves the same calls offline.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.db.models import Project  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.documents import ingest  # noqa: E402
from app.services.generation import generate  # noqa: E402

BRIEFS = ["demo_brief.md", "demo_brief_2.md"]

if __name__ == "__main__":
    s = get_settings()
    if s.llm_mode != "record":
        raise SystemExit("Run with LLM_MODE=record (make warm-cache does this).")
    with SessionLocal() as db:
        for name in BRIEFS:
            path = s.fixtures_dir / name
            p = Project(name=f"warm-cache {name}", status="draft", data_source="user")
            db.add(p)
            db.commit()
            doc = ingest(db, p.id, name, path.read_bytes(), None)
            for learning in (False, True):
                generate(db, p.id, [doc.id], learning, None, lambda x, m="", n=name: print(f"  {n} [{x:.0%}] {m}"))
                db.commit()
            db.delete(p)
            db.commit()
    print(f"cache written to {s.fixtures_dir / 'llm_cache'}")
