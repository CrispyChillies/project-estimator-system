"""Retrieval sanity check on the seeded DB: do nearest neighbours (other projects) share the task's category?"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.services.learning import active_model_key, load_records  # noqa: E402
from app.services.retrieval import cosine_rank  # noqa: E402


def main(top_k: int = 5) -> None:
    with SessionLocal() as db:
        recs = load_records(db, with_embeddings=True)
    items = [(t, r.id) for r in recs for t in r.tasks if t.embedding is not None]
    m = np.vstack([t.embedding for t, _ in items])
    hits, total, sims = 0, 0, []
    per_cat: Counter = Counter()
    per_cat_hit: Counter = Counter()
    for t, pid in items:
        s = cosine_rank(t.embedding, m)
        order = [j for j in np.argsort(-s) if items[j][1] != pid][:top_k]
        same = sum(items[j][0].category == t.category for j in order)
        hits += same
        total += len(order)
        sims.append(float(s[order[0]]))
        per_cat[t.category] += len(order)
        per_cat_hit[t.category] += same
    rate = hits / total
    print(f"model_key={active_model_key()} tasks={len(items)} top{top_k} same-category rate={rate:.3f} "
          f"median top-1 similarity={np.median(sims):.3f}")
    for c in sorted(per_cat):
        print(f"  {c:24s} {per_cat_hit[c] / per_cat[c]:.2f}")
    if rate < 0.6:
        raise SystemExit("FAIL: retrieval does not prefer same-category tasks")


if __name__ == "__main__":
    main()
