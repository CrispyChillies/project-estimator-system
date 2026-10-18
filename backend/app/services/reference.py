from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.templates import CATEGORY_NAMES
from app.db.models import DeliveryRole, Setting, TaskCategory, User
from app.services.settings import DEFAULTS

ROLES = [
    ("PM", 70, "#6366f1"), ("Designer", 60, "#ec4899"), ("Frontend", 60, "#06b6d4"),
    ("Backend", 65, "#22c55e"), ("Mobile", 65, "#f97316"), ("QA", 45, "#eab308"),
    ("DevOps", 75, "#8b5cf6"), ("ML/CV Engineer", 90, "#ef4444"), ("Data Engineer", 75, "#14b8a6"),
]

USERS = [
    ("Alice Martin", "alice@calibr.local", "pm"),
    ("Bob Nguyen", "bob@calibr.local", "pm"),
    ("Erin Admin", "admin@calibr.local", "admin"),
    ("Historical team", "history@calibr.local", "pm"),
]

HISTORY_EMAIL = "history@calibr.local"


def ensure_reference_data(db: Session) -> None:
    existing_roles = {r.name for r in db.scalars(select(DeliveryRole))}
    for name, rate, color in ROLES:
        if name not in existing_roles:
            db.add(DeliveryRole(name=name, hourly_rate=rate, currency="EUR", color=color))
    existing_cats = {c.key for c in db.scalars(select(TaskCategory))}
    for key, (name, desc) in CATEGORY_NAMES.items():
        if key not in existing_cats:
            db.add(TaskCategory(key=key, name=name, description=desc))
    existing_users = {u.email for u in db.scalars(select(User))}
    for name, email, role in USERS:
        if email not in existing_users:
            db.add(User(name=name, email=email, role=role))
    if db.get(Setting, "learning") is None:
        db.add(Setting(key="learning", value=DEFAULTS.model_dump()))
    db.commit()


def category_maps(db: Session) -> tuple[dict, dict]:
    cats = list(db.scalars(select(TaskCategory)))
    return {c.id: c.key for c in cats}, {c.key: c.id for c in cats}


def role_maps(db: Session) -> tuple[dict, dict]:
    roles = list(db.scalars(select(DeliveryRole)))
    return {r.id: r.name for r in roles}, {r.name: r.id for r in roles}
