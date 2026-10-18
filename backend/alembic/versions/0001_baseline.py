"""baseline schema

Revision ID: 0001
Revises:
"""
from alembic import op
from app.db import models  # noqa: F401
from app.db.base import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APPEND_ONLY = """
CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION '% is append-only/immutable', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=op.get_bind())
    op.execute(APPEND_ONLY)
    # Rows are never updated; they only disappear via cascade when a whole estimate/project is deleted.
    op.execute(
        "CREATE TRIGGER edit_events_append_only BEFORE UPDATE ON edit_events "
        "FOR EACH ROW EXECUTE FUNCTION forbid_mutation()"
    )
    op.execute(
        "CREATE TRIGGER task_ai_baselines_immutable BEFORE UPDATE ON task_ai_baselines "
        "FOR EACH ROW EXECUTE FUNCTION forbid_mutation()"
    )


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
    op.execute("DROP FUNCTION IF EXISTS forbid_mutation")
