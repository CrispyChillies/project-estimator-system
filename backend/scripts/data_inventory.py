"""Exact row counts per table, for data-preservation checks.

  python scripts/data_inventory.py snapshot <label>   # writes data/inventory/<label>.json
  python scripts/data_inventory.py compare <before> <after>  # prints a markdown table; exit 1 if any table shrank
"""

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "inventory"


def counts() -> dict[str, int]:
    eng = create_engine(get_settings().database_url)
    with eng.connect() as c:
        tables = [r[0] for r in c.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))]
        return {t: c.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one() for t in tables}


def main() -> int:
    cmd = sys.argv[1]
    if cmd == "snapshot":
        OUT.mkdir(parents=True, exist_ok=True)
        data = counts()
        (OUT / f"{sys.argv[2]}.json").write_text(json.dumps(data, indent=1, sort_keys=True))
        print(json.dumps(data, indent=1, sort_keys=True))
        return 0
    before = json.loads((OUT / f"{sys.argv[2]}.json").read_text())
    after = json.loads((OUT / f"{sys.argv[3]}.json").read_text())
    bad = 0
    print(f"| table | {sys.argv[2]} | {sys.argv[3]} | status |\n|---|---:|---:|---|")
    for t in sorted(set(before) | set(after)):
        b, a = before.get(t), after.get(t)
        ok = b is None or (a is not None and a >= b)
        bad += not ok
        print(f"| {t} | {b if b is not None else '—'} | {a if a is not None else '—'} | {'ok' if ok else 'SHRANK'} |")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
