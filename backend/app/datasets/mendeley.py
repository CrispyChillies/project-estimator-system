"""Adapter for Mendeley Data 'Software Projects User Stories Estimates with PRED & MMRE' (10.17632/ytmwsf2997).

Download URL and license were NOT verifiable at build time (the Mendeley API returned HTTP 503).
`fetch()` tries the public API; on failure it prints manual instructions. `load()` inspects the actual
columns and maps them by fuzzy header matching, refusing to guess when ambiguous.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from app.agents import templates as T
from app.agents.chains import run_estimation
from app.core.config import get_settings
from app.datasets.synthetic import SynthProject, SynthTask

log = logging.getLogger(__name__)
DATASET_ID = "ytmwsf2997"
API = f"https://data.mendeley.com/public-api/datasets/{DATASET_ID}"
PAGE = f"https://data.mendeley.com/datasets/{DATASET_ID}"


def raw_dir() -> Path:
    return get_settings().raw_data_dir / "mendeley"


def manual_instructions() -> str:
    return (f"Could not download the Mendeley dataset automatically.\n"
            f"  1. Open {PAGE} in a browser and check the license shown on the page.\n"
            f"  2. Download all files ('Download All').\n"
            f"  3. Unzip and place the CSV/XLSX file(s) in: {raw_dir()} (repo path: data/raw/mendeley/)\n"
            f"  4. Record the license in docs/DATASETS.md, then run `make seed` again.\n"
            f"Seeding continues with synthetic data only.")


def fetch() -> bool:
    d = raw_dir()
    d.mkdir(parents=True, exist_ok=True)
    if any(d.glob("*.csv")) or any(d.glob("*.xlsx")):
        print(f"Mendeley files already present in {d}")
        return True
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as c:
            meta = c.get(API)
            meta.raise_for_status()
            info = meta.json()
            (d / "metadata.json").write_text(json.dumps(info, indent=1))
            lic = (info.get("data_licence") or info.get("license") or {})
            print(f"License reported by Mendeley: {lic}")
            files = info.get("files") or []
            for f in files:
                url = (f.get("content_details") or {}).get("download_url") or f.get("download_url")
                name = f.get("filename") or f.get("name")
                if not url or not name:
                    continue
                r = c.get(url)
                r.raise_for_status()
                (d / Path(name).name).write_bytes(r.content)
                print(f"downloaded {name}")
        return any(d.glob("*.csv")) or any(d.glob("*.xlsx"))
    except Exception as e:  # network, 503, schema change
        print(f"Mendeley download failed: {type(e).__name__}: {e}")
        print(manual_instructions())
        return False


def _rows(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() == ".csv":
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
        return list(csv.DictReader(io.StringIO(text)))
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        it = ws.iter_rows(values_only=True)
        header = next(it, None)
        if not header:
            continue
        hdr = [str(h or "").strip() for h in header]
        for row in it:
            if any(v is not None for v in row):
                out.append({hdr[i]: ("" if v is None else str(v)) for i, v in enumerate(row) if i < len(hdr)})
    return out


def _match(cols: list[str], *patterns: str) -> str | None:
    for pat in patterns:
        for c in cols:
            if re.search(pat, c, re.I):
                return c
    return None


def inspect() -> dict:
    files = sorted([*raw_dir().glob("*.csv"), *raw_dir().glob("*.xlsx")])
    report = {}
    for f in files:
        rows = _rows(f)
        report[f.name] = {"rows": len(rows), "columns": list(rows[0].keys()) if rows else []}
    return report


def load(k: int = 3) -> list[SynthProject]:
    files = sorted([*raw_dir().glob("*.csv"), *raw_dir().glob("*.xlsx")])
    if not files:
        return []
    rows = [r for f in files for r in _rows(f)]
    cols = list(rows[0].keys()) if rows else []
    print(f"Mendeley columns found: {cols}")
    c_proj = _match(cols, r"^project", r"project")
    c_text = _match(cols, r"user ?story", r"story", r"description", r"title", r"requirement")
    c_actual = _match(cols, r"actual", r"real", r"spent")
    c_pp = _match(cols, r"poker", r"planning", r"estimat")
    if not all([c_proj, c_text, c_actual, c_pp]):
        raise SystemExit(f"Cannot map Mendeley columns {cols}. Edit app/datasets/mendeley.py:load() mapping.")
    print(f"Mapping: project={c_proj!r} story={c_text!r} actual={c_actual!r} planning_poker={c_pp!r}")
    by_proj: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        try:
            r["_actual"], r["_pp"] = float(r[c_actual]), float(r[c_pp])
        except (TypeError, ValueError):
            continue
        if r["_actual"] > 0 and r["_pp"] > 0 and (r.get(c_text) or "").strip():
            by_proj[str(r[c_proj]).strip()].append(r)
    out = []
    start = datetime(2022, 1, 3, tzinfo=UTC)
    for i, (pname, stories) in enumerate(sorted(by_proj.items())):
        tasks_in = []
        for j, s in enumerate(stories):
            text = s[c_text].strip()
            cat = T.classify(text)
            tasks_in.append({"key": f"story_{j + 1}", "title": text[:120], "description": text,
                             "category_key": cat, "role_name": T.CATEGORY_INFO[cat]["role"]})
        _, samples = run_estimation(tasks_in, f"Mendeley project {pname}", [], k)
        sp = SynthProject(name=f"Mendeley project {pname}", client="Mendeley dataset", domain="Industrial web/mobile",
                          brief="\n".join(f"- {t['description']}" for t in tasks_in),
                          started_at=start + timedelta(weeks=8 * i), delivered_at=start + timedelta(weeks=8 * i + 12))
        for t, s in zip(tasks_in, stories, strict=True):
            pp = s["_pp"]
            sp.tasks.append(SynthTask(
                key=t["key"], module="Backlog", title=t["title"], description=t["description"],
                category=t["category_key"], role=t["role_name"], raw_samples=samples[t["key"]] or [(4.0, 12.0)],
                final=(round(pp * 0.85 * 2) / 2 or 0.5, round(pp * 1.15 * 2) / 2 or 0.5), actual=s["_actual"]))
        out.append(sp)
    return out
