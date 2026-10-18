"""Pure helpers to turn synthetic projects into learning records without a DB."""

import statistics
import uuid

import numpy as np

from app.datasets.synthetic import SynthProject
from app.llm.gateway import hash_embedding
from app.services.learning import ProjectRec, TaskRec


def to_records(projects: list[SynthProject], author: str = "hist") -> list[ProjectRec]:
    out = []
    for p in projects:
        tasks = []
        for t in p.tasks:
            raw = (statistics.median(s[0] for s in t.raw_samples), statistics.median(s[1] for s in t.raw_samples)) \
                if t.raw_samples else (None, None)
            tasks.append(TaskRec(
                task_id=str(uuid.uuid4()), key=t.key, title=t.title, category=t.category, raw_min=raw[0], raw_max=raw[1],
                final_min=t.final[0] if t.final else None, final_max=t.final[1] if t.final else None,
                actual=t.actual if t.final else None, origin=t.origin,
                embedding=np.asarray(hash_embedding(f"{t.title}\n{t.description}", 256)),
            ))
        out.append(ProjectRec(id=str(uuid.uuid4()), name=p.name, data_source="synthetic", status="delivered",
                              author=author, date=p.delivered_at, estimate_id=str(uuid.uuid4()), tasks=tasks,
                              unplanned_hours=sum(u[2] for u in p.unplanned),
                              raw_samples={t.key: t.raw_samples for t in p.tasks if t.raw_samples}))
    return out
