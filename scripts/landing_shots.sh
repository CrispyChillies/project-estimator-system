#!/usr/bin/env bash
# Regenerates the landing/help screenshots from the real product:
#  1. restores the newest pre-Prompt-5 backup into a scratch database `calibr_shots` (dev data untouched)
#  2. starts the isolated stack (frontend production build, backend LLM_MODE=live by default — a few cents)
#  3. runs scripts/capture_landing_screenshots.ts as a fictional admin "Sam Rivera"
set -euo pipefail
cd "$(dirname "$0")/.."
DUMP=$(ls -t backups/calibr-pre-prompt5-*.dump | head -1)
docker compose exec -T db dropdb -U calibr --if-exists calibr_shots
docker compose exec -T db createdb -U calibr calibr_shots
docker compose exec -T db pg_restore -U calibr -d calibr_shots --no-owner < "$DUMP" || echo "pg_restore finished with warnings"
SHOTS_DB=postgresql+psycopg://calibr:calibr@localhost:5432/calibr_shots
(cd backend && DATABASE_URL="$SHOTS_DB" uv run alembic upgrade head >/dev/null)
# Keep only the fictional reference dataset: drop user-entered and test-run projects from the scratch copy only.
(cd backend && DATABASE_URL="$SHOTS_DB" uv run python - <<'PY'
from sqlalchemy import select
from app.db.session import SessionLocal, engine
from app.db.models import Project
assert engine.url.database == "calibr_shots"
with SessionLocal() as db:
    for p in db.scalars(select(Project).where(Project.data_source == "user")).all():
        db.delete(p)
    db.commit()
PY
)
E2E_DB=postgresql+psycopg://calibr:calibr@localhost:5432/calibr_shots E2E_LLM_MODE=${SHOTS_LLM_MODE:-live} E2E_FRONTEND=prod \
  E2E_ADMIN_NAME="Sam Rivera" STACK_CMD='pnpm exec tsx ../scripts/capture_landing_screenshots.ts' frontend/e2e/run.sh
