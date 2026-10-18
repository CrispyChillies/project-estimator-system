"""Synthetic historical projects with PLANTED, documented biases (see docs/DATASETS.md).

Ground truth per category (multiplicative):
  ACTUAL_BIAS[c] = actual / true_size_mid  (the raw LLM is unbiased w.r.t. true size up to size**0.5 and
                   per-task noise, so E[actual/raw] ~= ACTUAL_BIAS[c] * ~1.03)
  EDIT_BIAS[c]   = E[final / raw]    (what PMs change at quote time)
Tests assert that the learning system recovers these factors.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.agents.templates import CATEGORY_INFO, HIDDEN_TASKS, TEMPLATES

ACTUAL_BIAS = {
    "integration_3rd_party": 1.35, "crud_admin": 1 / 1.15, "ml_cv": 1.25, "payments": 1.20,
    "data_migration": 1.30, "testing_qa": 1.15, "pm_overhead": 1.10, "auth": 1.05, "ui_frontend": 1.08,
    "api_backend": 1.05, "notifications": 0.95, "reporting_analytics": 1.0, "infra_devops": 1.10,
    "design_ux": 1.0, "security_compliance": 1.15, "other": 1.0,
}
# PMs correct roughly half of the true bias in log space, except ml_cv where they add ~20%.
EDIT_BIAS = {c: math.exp(0.5 * math.log(b)) for c, b in ACTUAL_BIAS.items()}
EDIT_BIAS["ml_cv"] = 1.20
TASK_NOISE_SIGMA = 0.18
RAW_NOISE_SIGMA = 0.25
PROJECT_NOISE_SIGMA = 0.10
EDIT_NOISE_SIGMA = 0.08
EDIT_PROB = 0.65
UNPLANNED_SHARE = 0.12
MISSED_TASK = ("security_compliance", 1)  # AI often misses "Security hardening"; PMs add it

DOMAINS = [
    ("Retail", "e-commerce storefront"), ("Healthcare", "patient booking portal"), ("Logistics", "fleet tracking app"),
    ("Fintech", "personal finance dashboard"), ("Education", "online course platform"), ("Real estate", "property listing site"),
    ("Hospitality", "restaurant reservation app"), ("Manufacturing", "quality inspection system"),
    ("Media", "subscription content portal"), ("Non-profit", "donor management system"),
]
FEATURE_SETS = [
    ["auth", "crud_admin", "ui_frontend", "payments", "notifications"],
    ["auth", "api_backend", "integration_3rd_party", "reporting_analytics", "ui_frontend"],
    ["auth", "ml_cv", "api_backend", "ui_frontend", "data_migration"],
    ["crud_admin", "integration_3rd_party", "payments", "reporting_analytics", "notifications"],
    ["auth", "api_backend", "integration_3rd_party", "ml_cv", "ui_frontend", "security_compliance"],
]


@dataclass
class SynthTask:
    key: str
    module: str
    title: str
    description: str
    category: str
    role: str
    raw_samples: list[tuple[float, float]]
    final: tuple[float, float] | None  # None => PM removed it
    actual: float | None
    origin: str = "ai"
    reason_tag: str | None = None


@dataclass
class SynthProject:
    name: str
    client: str
    domain: str
    brief: str
    started_at: datetime
    delivered_at: datetime
    tasks: list[SynthTask] = field(default_factory=list)
    unplanned: list[tuple[str, str, float]] = field(default_factory=list)


def _r(x: float) -> float:
    return max(0.5, round(x * 2) / 2)


def generate(n: int = 20, seed: int = 2024, k: int = 3) -> list[SynthProject]:
    rng = random.Random(seed)
    start = datetime(2024, 1, 8, tzinfo=UTC)
    out = []
    for i in range(n):
        domain, product = DOMAINS[i % len(DOMAINS)]
        cats = FEATURE_SETS[i % len(FEATURE_SETS)][:]
        rng.shuffle(cats)
        cats = cats[: rng.randint(3, len(cats))]
        size = rng.uniform(0.8, 1.4)
        proj_noise = rng.gauss(0, PROJECT_NOISE_SIGMA)
        name = f"{domain} {product.title()} #{i + 1:02d}"
        p = SynthProject(name=name, client=f"Synthetic Client {chr(65 + i % 26)}{i // 26 or ''}", domain=domain,
                         brief="", started_at=start + timedelta(weeks=5 * i),
                         delivered_at=start + timedelta(weeks=5 * i + rng.randint(8, 16)))
        picks: list[tuple[str, int, str]] = []
        for c in cats:
            idxs = list(range(len(TEMPLATES[c])))
            rng.shuffle(idxs)
            for j in idxs[: min(2, len(idxs))]:
                picks.append((c, j, CATEGORY_INFO[c]["role"]))
            if c in ("api_backend", "payments", "auth") and ("ui_frontend", 1, "Frontend") not in picks:
                picks.append(("ui_frontend", 1, "Frontend"))
        picks.append(("design_ux", 1, "Designer"))
        for c, j in HIDDEN_TASKS:
            if (c, j, CATEGORY_INFO[c]["role"]) not in picks:
                picks.append((c, j, CATEGORY_INFO[c]["role"]))

        for c, j, role in picks:
            title, desc, mult = TEMPLATES[c][j]
            # The raw LLM only partly perceives project scale (size**0.5) and has idiosyncratic per-task noise;
            # history (analogs) can average that noise out.
            raw_mid = CATEGORY_INFO[c]["base"] * mult * size**0.5 * math.exp(rng.gauss(0, RAW_NOISE_SIGMA))
            true_mid = CATEGORY_INFO[c]["base"] * mult * size
            samples = []
            for _ in range(k):
                m = raw_mid * rng.uniform(0.9, 1.1)
                samples.append((round(m * 0.75, 1), round(m * 1.25, 1)))
            med_mid = sorted((a + b) / 2 for a, b in samples)[k // 2]
            module = "Delivery & quality" if (c, j) in HIDDEN_TASKS else f"{c.replace('_', ' ').title()}"
            # PM edit
            removed = c == "pm_overhead" and j == 1 and rng.random() < 0.3
            if removed:
                final = None
                reason = "reuse_existing_code"
            elif rng.random() < EDIT_PROB or c == "ml_cv":
                f = EDIT_BIAS[c] * math.exp(rng.gauss(0, EDIT_NOISE_SIGMA))
                final = (_r(med_mid * 0.75 * f), _r(med_mid * 1.25 * f))
                reason = ("underestimated_complexity" if f > 1.05 else "overestimated" if f < 0.95 else None)
                if c == "integration_3rd_party" and reason:
                    reason = "client_specific" if rng.random() < 0.4 else reason
            else:
                final = (_r(med_mid * 0.75), _r(med_mid * 1.25))
                reason = None
            actual = None
            if final is not None:
                actual = round(true_mid * ACTUAL_BIAS[c] * math.exp(rng.gauss(0, TASK_NOISE_SIGMA) + proj_noise), 1)
            p.tasks.append(SynthTask(f"{c}_{j}", module, title, desc, c, role, samples, final, actual,
                                     reason_tag=reason))
        if rng.random() < 0.6:  # PM adds a task the AI missed
            c, j = MISSED_TASK
            title, desc, mult = TEMPLATES[c][j]
            h = CATEGORY_INFO[c]["base"] * mult * size
            p.tasks.append(SynthTask(f"user_{c}_{j}", "Delivery & quality", title, desc, c, CATEGORY_INFO[c]["role"], [],
                                     (_r(h * 0.8), _r(h * 1.3)), round(h * 1.1 * math.exp(rng.gauss(0, 0.2)), 1),
                                     origin="user", reason_tag="scope_added"))
        planned = sum(t.actual or 0 for t in p.tasks)
        unplanned_total = planned * UNPLANNED_SHARE / (1 - UNPLANNED_SHARE) * math.exp(rng.gauss(0, 0.3))
        p.unplanned = [("Change requests after UAT", "other", round(unplanned_total * 0.6, 1)),
                       ("Additional client meetings", "pm_overhead", round(unplanned_total * 0.4, 1))]
        p.brief = _brief(p, product, rng)
        out.append(p)
    return out


def _brief(p: SynthProject, product: str, rng: random.Random) -> str:
    lines = [f"# {p.name}", "", f"{p.client} wants to build a {product} for the {p.domain.lower()} sector.", "",
             "## Requirements"]
    for t in p.tasks:
        if t.origin == "ai" and t.module != "Delivery & quality":
            lines.append(f"- {t.description}")
    lines += ["", "## Notes", "- Launch target in about three months.",
              f"- Budget is {'tight' if rng.random() < 0.5 else 'flexible'}; prefer proven technology."]
    return "\n".join(lines)
