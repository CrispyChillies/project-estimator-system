"""Default VND billing-rate card (Vietnam market, derived in docs/RATES_VN.md) and per-user effective rates."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DeliveryRole, TaskCategory, User

# Hourly billing rate in whole VND = median monthly gross × 0.015837, rounded to 10.000 ₫ (see docs/RATES_VN.md).
DEFAULT_RATES_VND: dict[str, int] = {
    "PM": 790_000, "Designer": 550_000, "Frontend": 550_000, "Backend": 600_000, "Mobile": 580_000,
    "QA": 490_000, "DevOps": 670_000, "ML/CV Engineer": 830_000, "Data Engineer": 650_000,
}

PALETTE = ("blue", "sky", "cyan", "teal", "emerald", "green", "lime", "yellow", "amber", "orange", "red", "rose",
           "pink", "fuchsia", "purple", "violet", "indigo", "slate", "gray", "stone")

ROLE_COLORS = {"PM": "amber", "Designer": "pink", "Frontend": "sky", "Backend": "indigo", "Mobile": "orange",
               "QA": "lime", "DevOps": "slate", "ML/CV Engineer": "purple", "Data Engineer": "teal"}

# Colour families: related categories look related but stay distinguishable.
CATEGORY_COLORS = {
    "ui_frontend": "blue", "crud_admin": "sky",  # blues
    "api_backend": "indigo", "data_migration": "violet",
    "integration_3rd_party": "teal", "notifications": "cyan",  # teal family
    "payments": "emerald",  # green
    "ml_cv": "purple", "reporting_analytics": "fuchsia",  # data / ML
    "infra_devops": "slate", "testing_qa": "lime", "design_ux": "pink",
    "security_compliance": "red", "auth": "orange",  # security
    "pm_overhead": "amber", "other": "gray",
}


def next_unused_color(used: set[str]) -> str:
    return next((c for c in PALETTE if c not in used), PALETTE[len(used) % len(PALETTE)])


def apply_vn_defaults(db: Session) -> None:
    """Idempotent: fills only rows that have no VND rate / no token colour yet. Never overwrites user choices."""
    for r in db.scalars(select(DeliveryRole)):
        if not r.hourly_rate_vnd and r.name in DEFAULT_RATES_VND:
            r.hourly_rate_vnd = DEFAULT_RATES_VND[r.name]
        if r.color not in PALETTE:
            r.color = ROLE_COLORS.get(r.name) or next_unused_color({x.color for x in db.scalars(select(DeliveryRole))})
    for c in db.scalars(select(TaskCategory)):
        if c.color not in PALETTE:
            c.color = CATEGORY_COLORS.get(c.key, "gray")
    db.commit()


def effective_rates(db: Session, user: User | None) -> dict[uuid.UUID, int]:
    """role_id -> VND/h for this user: their own override, else the workspace default."""
    over = (user.rate_overrides if user is not None else None) or {}
    out: dict[uuid.UUID, int] = {}
    for r in db.scalars(select(DeliveryRole)):
        v = over.get(str(r.id))
        out[r.id] = int(v) if isinstance(v, int | float) and v > 0 else int(r.hourly_rate_vnd or 0)
    return out
