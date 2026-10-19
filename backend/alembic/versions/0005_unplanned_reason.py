"""Unplanned work reason + onboarding progress (additive)

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

REASONS = ("missed_requirement", "clarified_scope", "change_request", "other", "unspecified")


def upgrade() -> None:
    op.execute("ALTER TABLE unplanned_actuals ADD COLUMN IF NOT EXISTS reason VARCHAR(30) NOT NULL DEFAULT 'unspecified'")
    allowed = ",".join(f"'{r}'" for r in REASONS)
    op.execute("ALTER TABLE unplanned_actuals DROP CONSTRAINT IF EXISTS ck_unplanned_actuals_reason")
    op.execute(f"ALTER TABLE unplanned_actuals ADD CONSTRAINT ck_unplanned_actuals_reason CHECK (reason IN ({allowed}))")


def downgrade() -> None:
    op.execute("ALTER TABLE unplanned_actuals DROP COLUMN IF EXISTS reason")
