"""Idempotent demo seed: reference data, synthetic history, optional Mendeley dataset, learning recompute."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.datasets import mendeley, synthetic  # noqa: E402
from app.datasets.loader import load_project  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.learning import propose_lessons, recompute  # noqa: E402
from app.services.reference import ensure_archive_users, ensure_reference_data  # noqa: E402


def main() -> None:
    with SessionLocal() as db:
        ensure_reference_data(db)
        ensure_archive_users(db)
        n_new = 0
        for sp in synthetic.generate():
            if load_project(db, sp, "synthetic"):
                n_new += 1
                db.commit()
        print(f"synthetic projects added: {n_new}")
        try:
            projects = mendeley.load(k=3)
        except SystemExit as e:
            print(e)
            projects = []
        if not projects:
            print("Mendeley dataset not present (run `make fetch-datasets`); skipping.")
        m_new = 0
        for sp in projects:
            if load_project(db, sp, "dataset"):
                m_new += 1
                db.commit()
        print(f"dataset projects added: {m_new}")
        if n_new or m_new:
            recompute(db, "manual")
            rules = propose_lessons(db)
            db.commit()
            print(f"proposed rules: {len(rules)}")
        print("seed complete")


if __name__ == "__main__":
    main()
