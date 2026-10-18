"""LLM chains: extraction, decomposition, estimation, lessons. Each has a deterministic fake twin."""

from __future__ import annotations

import re
import statistics

from app.agents import templates as T
from app.agents.schemas import (
    DecomposedModule,
    DecomposedTask,
    Decomposition,
    EstimationResult,
    ExtractionResult,
    Lesson,
    LessonsResult,
    Requirement,
    ScenarioTask,
    TaskHours,
    Unknown,
)
from app.llm.gateway import get_gateway
from app.prompts import PROMPT_VERSIONS, render

UNCERTAIN = re.compile(r"\?|\b(maybe|possibly|might|tbd|not sure|optional|later|nice to have|perhaps)\b", re.I)
REQ_HINT = re.compile(r"^\s*([-*•]|\d+[.)])|\b(should|must|need|needs|want|wants|will|require|allow)\b", re.I)
# Per-run diagnostics read by the model bake-off (first-attempt citation validity).
EXTRACTION_STATS: list[dict] = []


def _sentences(text: str) -> list[str]:
    parts: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^\s*([-*•]|\d+[.)])", line):
            parts.append(line)
        else:
            parts.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", line) if s.strip())
    return parts


# ---------------- extraction ----------------
def fake_extraction(chunks: list[tuple[str, str]]) -> ExtractionResult:
    reqs: list[Requirement] = []
    unknowns: list[Unknown] = []
    out_scope: list[str] = []
    for cid, text in chunks:
        for s in _sentences(text):
            clean = re.sub(r"^\s*([-*•]|\d+[.)])\s*", "", s).strip()
            if len(clean.split()) < 3:
                continue
            if re.search(r"out of scope|not needed|no need|excluded", clean, re.I):
                out_scope.append(clean)
                continue
            if UNCERTAIN.search(clean):
                cat = T.classify(clean)
                info = T.CATEGORY_INFO[cat]
                base = info["base"]
                unknowns.append(Unknown(
                    question=f"Is this required: \"{clean[:140]}\"",
                    why_it_matters=f"Would add {T.CATEGORY_NAMES[cat][0].lower()} work.",
                    scenario_if_yes=[ScenarioTask(title=T.TEMPLATES[cat][T.pick_template(cat, clean)][0],
                                                  category_key=cat, role_name=info["role"],
                                                  min_hours=base * 0.7, max_hours=base * 1.4)],
                    prior_probability=0.5 if "?" in clean else 0.35,
                ))
                continue
            if REQ_HINT.search(s) or T.classify(clean) != "other":
                reqs.append(Requirement(id=f"R{len(reqs) + 1}", text=clean, source_chunk_ids=[cid]))
    if not reqs and chunks:
        reqs.append(Requirement(id="R1", text=chunks[0][1][:300], source_chunk_ids=[chunks[0][0]]))
    summary = " ".join(_sentences(chunks[0][1])[:2])[:400] if chunks else ""
    return ExtractionResult(
        summary=summary, requirements=reqs,
        assumptions=["Client provides content and API credentials on time.",
                     "Standard browser support (latest two versions)."],
        risks=[f"Third-party dependency: {r.text[:120]}" for r in reqs
               if T.classify(r.text) == "integration_3rd_party"][:3],
        out_of_scope=out_scope, unknowns=unknowns[:8],
    )


def run_extraction(chunks: list[tuple[str, str]], categories: list[str], roles: list[str]) -> ExtractionResult:
    gw = get_gateway()
    valid = {cid for cid, _ in chunks}
    prompt = render("extraction", categories=", ".join(categories), roles=", ".join(roles),
                    chunks="\n\n".join(f"[{cid}] {text}" for cid, text in chunks))
    messages = [("system", "You extract structured requirements. Output must follow the schema."), ("user", prompt)]
    result = None
    for attempt in range(2):
        result = gw.structured("extraction", messages, ExtractionResult, prompt_version=PROMPT_VERSIONS["extraction"],
                               fake=lambda: fake_extraction(chunks), temperature=0.0, sample_idx=attempt)
        bad = [c for r in result.requirements for c in r.source_chunk_ids if c not in valid]
        uncited = sum(1 for r in result.requirements if not r.source_chunk_ids)
        if attempt == 0:
            EXTRACTION_STATS.append({"citations": sum(len(r.source_chunk_ids) for r in result.requirements),
                                     "invalid_citations": len(bad), "uncited_requirements": uncited,
                                     "requirements": len(result.requirements), "attempts": 1})
        else:
            EXTRACTION_STATS[-1]["attempts"] = 2
        if not bad and not uncited:
            return result
        messages = [*messages, ("user", f"Invalid or missing chunk ids {bad[:5]}. Cite only: {sorted(valid)}.")]
    assert result is not None
    for r in result.requirements:  # second failure: keep only valid citations
        r.source_chunk_ids = [c for c in r.source_chunk_ids if c in valid]
    return result


# ---------------- decomposition ----------------
def fake_decomposition(ex: ExtractionResult) -> Decomposition:
    modules: dict[str, DecomposedModule] = {}
    used: set[tuple[str, int]] = set()
    for r in ex.requirements:
        cat = T.classify(r.text)
        if cat in ("other",):
            cat = "api_backend"
        idx = T.pick_template(cat, r.text)
        if (cat, idx) in used:
            continue
        used.add((cat, idx))
        title, desc, _ = T.TEMPLATES[cat][idx]
        mod_name = T.CATEGORY_NAMES[cat][0]
        modules.setdefault(mod_name, DecomposedModule(name=mod_name, tasks=[]))
        modules[mod_name].tasks.append(DecomposedTask(
            key=f"{cat}_{idx}", title=title, description=desc, category_key=cat,
            role_name=T.CATEGORY_INFO[cat]["role"], rationale=f"From requirement: {r.text[:200]}",
            requirement_ids=[r.id], confidence="medium",
        ))
        # UI work for backend features
        if cat in ("api_backend", "payments", "auth") and ("ui_frontend", 1) not in used:
            used.add(("ui_frontend", 1))
            t2, d2, _ = T.TEMPLATES["ui_frontend"][1]
            modules[mod_name].tasks.append(DecomposedTask(
                key="ui_frontend_1", title=t2, description=d2, category_key="ui_frontend", role_name="Frontend",
                rationale="User-facing screens for the backend features.", requirement_ids=[r.id]))
    if ("design_ux", 1) not in used:
        t, d, _ = T.TEMPLATES["design_ux"][1]
        modules.setdefault("Design", DecomposedModule(name="Design", tasks=[])).tasks.append(DecomposedTask(
            key="design_ux_1", title=t, description=d, category_key="design_ux", role_name="Designer",
            rationale="Every client-facing product needs UI design."))
    hidden = DecomposedModule(name="Delivery & quality", description="Hidden but necessary work", tasks=[])
    for cat, idx in T.HIDDEN_TASKS:
        if (cat, idx) in used:
            continue
        t, d, _ = T.TEMPLATES[cat][idx]
        hidden.tasks.append(DecomposedTask(key=f"{cat}_{idx}", title=t, description=d, category_key=cat,
                                           role_name=T.CATEGORY_INFO[cat]["role"],
                                           rationale="Standard delivery task (often forgotten).", confidence="high"))
    return Decomposition(modules=[*modules.values(), hidden])


def run_decomposition(ex: ExtractionResult, categories: list[str], roles: list[str], rules: list[str]) -> Decomposition:
    prompt = render(
        "decomposition", categories=", ".join(categories), roles=", ".join(roles),
        requirements="\n".join(f"{r.id}: {r.text}" for r in ex.requirements),
        assumptions="; ".join(ex.assumptions) or "none", out_of_scope="; ".join(ex.out_of_scope) or "none",
        rules="\n".join(f"- {r}" for r in rules) or "none",
    )
    result = get_gateway().structured(
        "decomposition", [("system", "You decompose software projects."), ("user", prompt)], Decomposition,
        prompt_version=PROMPT_VERSIONS["decomposition"], fake=lambda: fake_decomposition(ex), temperature=0.1,
    )
    seen: set[str] = set()
    for m in result.modules:  # enforce unique keys and valid taxonomy
        for t in m.tasks:
            base, i = re.sub(r"[^a-z0-9_]", "_", t.key.lower())[:60] or "task", 2
            key = base
            while key in seen:
                key, i = f"{base}_{i}", i + 1
            t.key = key
            seen.add(key)
            if t.category_key not in categories:
                t.category_key = "other"
            if t.role_name not in roles:
                t.role_name = T.CATEGORY_INFO.get(t.category_key, T.CATEGORY_INFO["other"])["role"]
    return result


# ---------------- estimation ----------------
def fake_estimation(tasks: list[dict], sample_idx: int) -> EstimationResult:
    out = []
    for t in tasks:
        cat = t["category_key"]
        base = T.CATEGORY_INFO.get(cat, T.CATEGORY_INFO["other"])["base"]
        mult = 1.0
        for title, _, m in T.TEMPLATES.get(cat, []):
            if title == t["title"]:
                mult = m
        noise = 0.9 + 0.2 * T.stable_unit(t["key"], t["title"], sample_idx)
        m_ = base * mult * noise
        out.append(TaskHours(task_key=t["key"], min_hours=round(m_ * 0.75, 1), max_hours=round(m_ * 1.25, 1)))
    return EstimationResult(estimates=out)


def run_estimation(tasks: list[dict], summary: str, rules: list[str], k: int) -> tuple[dict[str, tuple[float, float]], dict]:
    """Run K samples on a fixed task list; return per-task median (min, max) and all samples."""
    prompt = render(
        "estimation", summary=summary, rules="\n".join(f"- {r}" for r in rules) or "none",
        tasks="\n".join(f"{t['key']} | {t['role_name']} | {t['category_key']} | {t['title']} — {t['description']}"
                        for t in tasks),
    )
    samples: dict[str, list[tuple[float, float]]] = {t["key"]: [] for t in tasks}
    for i in range(k):
        res = get_gateway().structured(
            "estimation", [("system", "You estimate software tasks in hours."), ("user", prompt)], EstimationResult,
            prompt_version=PROMPT_VERSIONS["estimation"], fake=lambda i=i: fake_estimation(tasks, i),
            temperature=0.7 if k > 1 else 0.0, sample_idx=i,
        )
        for e in res.estimates:
            if e.task_key in samples:
                lo, hi = sorted((e.min_hours, e.max_hours))
                samples[e.task_key].append((max(lo, 0.25), max(hi, 0.5)))
    medians: dict[str, tuple[float, float]] = {}
    for key, ss in samples.items():
        if not ss:  # LLM dropped a task: fall back to category base, flagged in samples
            ss = [(4.0, 12.0)]
            samples[key] = []
        medians[key] = (statistics.median(s[0] for s in ss), statistics.median(s[1] for s in ss))
    return medians, samples


# ---------------- lessons ----------------
def fake_lessons(evidence: list[dict]) -> LessonsResult:
    rules = []
    for e in evidence:
        if e.get("kind") != "category_bias" or e["n"] < 4 or abs(e["mean_pct"]) < 10:
            continue
        direction = "underestimated" if e["mean_pct"] > 0 else "overestimated"
        who = "PMs adjusted" if e["layer"] == "edit" else "actual hours exceeded" if e["mean_pct"] > 0 else "actual hours were below"
        reason = f" (common reason: {e['top_reason'].replace('_', ' ')})" if e.get("top_reason") else ""
        rules.append(Lesson(
            text=f"{e['category_name']} tasks are usually {direction} by ~{abs(e['mean_pct']):.0f}% by the raw AI: "
                 f"{who} {e['n_dir']} of {e['n']} such tasks{reason}.",
            layer=e["layer"], category_key=e["category"], evidence_count=e["n"]))
    for e in evidence:
        if e.get("kind") == "missing_task" and e["count"] >= 2:
            rules.append(Lesson(text=f"PMs repeatedly add '{e['title']}' ({e['category_name']}) that the AI misses; "
                                     f"include it when relevant.", layer="edit", category_key=e["category"],
                                evidence_count=e["count"]))
    return LessonsResult(rules=rules[:5])


def run_lessons(evidence: list[dict]) -> LessonsResult:
    import json

    prompt = render("lessons", evidence=json.dumps(evidence, indent=1, default=str)[:12000])
    return get_gateway().structured(
        "lessons", [("system", "You distill estimation lessons."), ("user", prompt)], LessonsResult,
        prompt_version=PROMPT_VERSIONS["lessons"], fake=lambda: fake_lessons(evidence), temperature=0.0,
    )
