"""VND as canonical currency, per-user display currency/rate overrides/tag colours, category colours (additive)

Revision ID: 0006
Revises: 0005
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE delivery_roles ADD COLUMN IF NOT EXISTS hourly_rate_vnd BIGINT NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE task_categories ADD COLUMN IF NOT EXISTS color VARCHAR(20) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_currency VARCHAR(3) NOT NULL DEFAULT 'VND'")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS rate_overrides JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS tag_colors JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_display_currency")
    op.execute("ALTER TABLE users ADD CONSTRAINT ck_users_display_currency CHECK (display_currency IN ('VND','USD'))")


def downgrade() -> None:
    for t, c in (("delivery_roles", "hourly_rate_vnd"), ("task_categories", "color"), ("users", "display_currency"),
                 ("users", "rate_overrides"), ("users", "tag_colors")):
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS {c}")
