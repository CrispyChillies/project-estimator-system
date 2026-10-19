"""Accounts, sessions, ownership and sharing (additive; existing data is archived to the admin)

Revision ID: 0004
Revises: 0003
"""
from alembic import op
from app.db import enums as E

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

NEW_TABLES = ["sessions", "project_members", "login_attempts", "password_resets"]

COLUMNS = [
    ("users", "password_hash VARCHAR(255)"),
    ("users", "is_active BOOLEAN NOT NULL DEFAULT true"),
    ("users", "archived BOOLEAN NOT NULL DEFAULT false"),
    ("users", "last_login_at TIMESTAMPTZ"),
    ("users", "onboarding_state JSONB NOT NULL DEFAULT '{}'::jsonb"),
    ("users", "daily_usd_cap DOUBLE PRECISION"),
    ("projects", "owner_id UUID REFERENCES users(id)"),
    ("projects", "is_archive BOOLEAN NOT NULL DEFAULT false"),
    ("projects", "shared_to_workspace BOOLEAN NOT NULL DEFAULT false"),
    ("jobs", "user_id UUID"),
    ("backtest_runs", "owner_id UUID"),
    ("learned_rules", "owner_id UUID"),
    ("calibration_runs", "owner_id UUID"),
    ("llm_calls", "user_id UUID"),
]


def upgrade() -> None:
    import app.db.models  # noqa: F401
    from app.db.base import Base

    Base.metadata.create_all(op.get_bind(), tables=[Base.metadata.tables[t] for t in NEW_TABLES], checkfirst=True)
    for table, col in COLUMNS:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col}")
    for t, c in [("projects", "owner_id"), ("jobs", "user_id"), ("backtest_runs", "owner_id"),
                 ("learned_rules", "owner_id"), ("calibration_runs", "owner_id"), ("llm_calls", "user_id")]:
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{t}_{c} ON {t} ({c})")
    roles = ",".join(f"'{r}'" for r in E.USER_ROLES)
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role")
    op.execute(f"ALTER TABLE users ADD CONSTRAINT ck_users_role CHECK (role IN ({roles}))")
    # Everything that exists before accounts is archived test data; the admin (created at startup) owns it.
    op.execute("UPDATE projects SET is_archive = true WHERE owner_id IS NULL")
    # Pre-account users stay for edit-log integrity but can never sign in.
    op.execute("UPDATE users SET is_active = false, archived = true WHERE password_hash IS NULL")


def downgrade() -> None:
    for t in NEW_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {t}")
    for table, col in COLUMNS:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col.split()[0]}")
