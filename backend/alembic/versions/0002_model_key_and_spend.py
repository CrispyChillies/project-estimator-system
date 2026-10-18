"""model_key partitioning and spend accounting columns

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# IF NOT EXISTS: 0001 builds from current metadata, so fresh databases already have these columns.
STATEMENTS = [
    "ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS model_key VARCHAR(160)",
    "ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS section VARCHAR(60)",
    "ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS cached_tokens INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS reasoning_tokens INTEGER NOT NULL DEFAULT 0",
    "CREATE INDEX IF NOT EXISTS ix_llm_calls_model_key ON llm_calls (model_key)",
    "CREATE INDEX IF NOT EXISTS ix_llm_calls_section ON llm_calls (section)",
    "ALTER TABLE estimates ADD COLUMN IF NOT EXISTS model_key VARCHAR(160) NOT NULL DEFAULT 'fake-v1'",
    "CREATE INDEX IF NOT EXISTS ix_estimates_model_key ON estimates (model_key)",
    "ALTER TABLE task_ai_baselines DISABLE TRIGGER task_ai_baselines_immutable",
    "ALTER TABLE task_ai_baselines ADD COLUMN IF NOT EXISTS model_key VARCHAR(160) NOT NULL DEFAULT 'fake-v1'",
    "ALTER TABLE task_ai_baselines ENABLE TRIGGER task_ai_baselines_immutable",
    "ALTER TABLE llm_raw_estimates ADD COLUMN IF NOT EXISTS model_key VARCHAR(160) NOT NULL DEFAULT 'fake-v1'",
    "CREATE INDEX IF NOT EXISTS ix_llm_raw_estimates_model_key ON llm_raw_estimates (model_key)",
]


def upgrade() -> None:
    for s in STATEMENTS:
        op.execute(s)


def downgrade() -> None:
    for t, c in [("llm_calls", "model_key"), ("llm_calls", "section"), ("llm_calls", "cached_tokens"),
                 ("llm_calls", "reasoning_tokens"), ("estimates", "model_key"), ("task_ai_baselines", "model_key"),
                 ("llm_raw_estimates", "model_key")]:
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS {c}")
