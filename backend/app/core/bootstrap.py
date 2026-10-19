"""Startup: fail-fast config validation, reference data, first admin from env, archive ownership backfill."""

from __future__ import annotations

import logging

from sqlalchemy import select, text

from app.core.config import Settings

log = logging.getLogger("app")


class ConfigError(RuntimeError):
    pass


def validate_config(s: Settings) -> None:
    problems: list[str] = []
    if s.signup_mode not in ("open", "invite", "closed"):
        problems.append("SIGNUP_MODE must be open, invite or closed")
    if s.signup_mode == "invite" and s.is_production and len(s.invite_code) < 8:
        problems.append("INVITE_CODE must be set (8+ characters) when SIGNUP_MODE=invite")
    if s.is_production:
        if s.llm_mode != "live":
            problems.append(f"LLM_MODE must be 'live' in production (got '{s.llm_mode}'); fake/replay are test-only")
        if len(s.session_secret) < 32:
            problems.append("SESSION_SECRET must be at least 32 characters")
        if not s.openai_api_key or not s.openai_model or not s.openai_embedding_model:
            problems.append("OPENAI_API_KEY, OPENAI_MODEL and OPENAI_EMBEDDING_MODEL are required")
        if not s.database_url.startswith("postgresql"):
            problems.append("DATABASE_URL must be a PostgreSQL URL")
        if s.llm_budget_usd <= 0:
            problems.append("LLM_BUDGET_USD must be positive")
    if problems:
        raise ConfigError("Invalid configuration:\n- " + "\n- ".join(problems))


def ensure_admin(db, s: Settings) -> None:
    from app.core.auth import hash_password, password_problem
    from app.db.models import User

    if db.scalar(select(User.id).where(User.role == "admin", User.is_active.is_(True), User.archived.is_(False),
                                       User.password_hash.is_not(None))):
        return
    if not s.admin_email or not s.admin_password:
        if s.is_production:
            raise ConfigError("No admin exists: set ADMIN_EMAIL and ADMIN_PASSWORD")
        log.warning("no admin account: set ADMIN_EMAIL and ADMIN_PASSWORD to create one")
        return
    email = s.admin_email.strip().lower()
    if problem := password_problem(s.admin_password, email):
        raise ConfigError(f"ADMIN_PASSWORD is too weak: {problem}")
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        existing.role, existing.is_active, existing.archived = "admin", True, False
        existing.password_hash = hash_password(s.admin_password)
    else:
        db.add(User(name="Administrator", email=email, role="admin", password_hash=hash_password(s.admin_password),
                    is_active=True, onboarding_state={"tour_done": True, "welcome_seen": True}))
    db.commit()
    log.info("admin account created", extra={"extra": {"email_domain": email.split("@")[-1]}})


def backfill_ownership(db) -> None:
    """Pre-account data belongs to the first admin (idempotent: only rows without an owner)."""
    from app.db.models import User

    admin_id = db.scalar(select(User.id).where(User.role == "admin", User.archived.is_(False))
                         .order_by(User.created_at))
    if admin_id is None:
        return
    for table, col in (("projects", "owner_id"), ("backtest_runs", "owner_id"), ("learned_rules", "owner_id"),
                       ("calibration_runs", "owner_id")):
        db.execute(text(f"UPDATE {table} SET {col} = :a WHERE {col} IS NULL"), {"a": admin_id})
    db.commit()


def bootstrap() -> None:
    from app.core.config import get_settings
    from app.db.session import SessionLocal
    from app.services.learning import ensure_calibration_for_active_model
    from app.services.reference import ensure_reference_data

    s = get_settings()
    with SessionLocal() as db:
        ensure_reference_data(db)
        ensure_admin(db, s)
        backfill_ownership(db)
        ensure_calibration_for_active_model(db)
