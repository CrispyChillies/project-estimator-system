"""Agent operations, session memory, project retrieval tables

Revision ID: 0003
Revises: 0002
"""
from alembic import op
from app.db import enums as E

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

NEW_TABLES = ["agent_operations", "project_memories", "project_embeddings", "retrieval_logs"]

# IF NOT EXISTS everywhere: 0001 builds from current metadata, so fresh databases already have all of this.
COLUMNS = [
    ("tasks", "row_version INTEGER NOT NULL DEFAULT 1"),
    ("edit_events", "operation_id UUID"),
    ("edit_events", "batch_id UUID"),
    ("edit_events", "session_id UUID"),
    ("agent_sessions", "title VARCHAR(200) NOT NULL DEFAULT 'New session'"),
    ("agent_sessions", "summary TEXT NOT NULL DEFAULT ''"),
    ("agent_sessions", "summary_upto_message_id UUID"),
    ("agent_sessions", "state JSONB NOT NULL DEFAULT '{}'::jsonb"),
    ("agent_sessions", "status VARCHAR(10) NOT NULL DEFAULT 'active'"),
    ("agent_sessions", "pinned BOOLEAN NOT NULL DEFAULT false"),
    ("agent_sessions", "apply_mode VARCHAR(10) NOT NULL DEFAULT 'auto'"),
    ("agent_sessions", "use_memory BOOLEAN NOT NULL DEFAULT true"),
    ("agent_sessions", "model_key VARCHAR(160)"),
    ("agent_sessions", "run_state VARCHAR(20) NOT NULL DEFAULT 'idle'"),
    ("agent_sessions", "cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0"),
    ("agent_sessions", "tokens INTEGER NOT NULL DEFAULT 0"),
    ("agent_sessions", "last_activity_at TIMESTAMPTZ"),
    ("agent_messages", "payload JSONB NOT NULL DEFAULT '{}'::jsonb"),
    ("agent_messages", "batch_id UUID"),
    ("agent_messages", "estimate_version INTEGER"),
    ("agent_messages", "input_tokens INTEGER NOT NULL DEFAULT 0"),
    ("agent_messages", "output_tokens INTEGER NOT NULL DEFAULT 0"),
    ("agent_messages", "idempotency_key VARCHAR(80)"),
]


def upgrade() -> None:
    import app.db.models  # noqa: F401
    from app.db.base import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind, tables=[Base.metadata.tables[t] for t in NEW_TABLES], checkfirst=True)
    for table, col in COLUMNS:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col}")
    op.execute("CREATE INDEX IF NOT EXISTS ix_edit_events_operation_id ON edit_events (operation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_edit_events_batch_id ON edit_events (batch_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_messages_idempotency_key ON agent_messages (idempotency_key)")
    op.execute("ALTER TABLE task_ai_baselines DISABLE TRIGGER task_ai_baselines_immutable")
    op.execute("ALTER TABLE task_ai_baselines ADD COLUMN IF NOT EXISTS retrieval JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE task_ai_baselines ENABLE TRIGGER task_ai_baselines_immutable")
    allowed = ",".join(f"'{v}'" for v in E.EVENT_TYPES)
    op.execute("ALTER TABLE edit_events DROP CONSTRAINT IF EXISTS ck_edit_events_event_type")
    op.execute(f"ALTER TABLE edit_events ADD CONSTRAINT ck_edit_events_event_type CHECK (event_type IN ({allowed}))")
    for name, vals in [("status", ("active", "archived", "deleted")), ("apply_mode", ("auto", "review"))]:
        op.execute(f"ALTER TABLE agent_sessions DROP CONSTRAINT IF EXISTS ck_agent_sessions_{name}")
        v = ",".join(f"'{x}'" for x in vals)
        op.execute(f"ALTER TABLE agent_sessions ADD CONSTRAINT ck_agent_sessions_{name} CHECK ({name} IN ({v}))")


def downgrade() -> None:
    for t in NEW_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {t}")
    for table, col in COLUMNS:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col.split()[0]}")
