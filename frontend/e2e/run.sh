#!/usr/bin/env bash
# Starts an isolated stack for browser tests and runs Playwright against it:
#  - backend :8010 on database calibr_e2e (a copy of the archive; never the dev DB), LLM_MODE=fake (deterministic, $0)
#  - frontend dev server :3005 proxying /api to :8010
# A random admin password is generated per run and only passed through the environment.
set -euo pipefail
cd "$(dirname "$0")/../.."
E2E_DB=${E2E_DB:-postgresql+psycopg://calibr:calibr@localhost:5432/calibr_e2e}
export E2E_ADMIN_EMAIL=e2e-admin@example.com
export E2E_ADMIN_PASSWORD="e2e-$(openssl rand -hex 12)"
(cd backend && DATABASE_URL="$E2E_DB" uv run alembic upgrade head >/dev/null)
(cd backend && DATABASE_URL="$E2E_DB" uv run python - <<'PY'
from app.db.session import SessionLocal
from app.db.models import User, AuthSession
import os
from app.core.auth import hash_password
with SessionLocal() as db:  # create/reset the e2e admin for this run (e2e database only)
    email = os.environ["E2E_ADMIN_EMAIL"]
    u = db.query(User).filter(User.email == email).first()
    if u is None:
        u = User(name=os.environ.get("E2E_ADMIN_NAME", "E2E Admin"), email=email, role="admin", onboarding_state={"tour_done": True, "welcome_seen": True})
        db.add(u)
    u.name = os.environ.get("E2E_ADMIN_NAME", "E2E Admin"); u.password_hash = hash_password(os.environ["E2E_ADMIN_PASSWORD"]); u.is_active = True; u.role = "admin"; u.archived = False
    db.flush()
    db.query(AuthSession).filter(AuthSession.user_id == u.id).delete()
    db.commit()
PY
)
(cd backend && DATABASE_URL="$E2E_DB" LLM_MODE=${E2E_LLM_MODE:-fake} APP_ENV=test SIGNUP_MODE=open USER_HOURLY_REQUESTS=1000 \
  MAX_CONCURRENT_RUNS_PER_USER=5 ADMIN_EMAIL="$E2E_ADMIN_EMAIL" ADMIN_PASSWORD="$E2E_ADMIN_PASSWORD" \
  uv run uvicorn app.main:app --port 8010 >/tmp/calibr-e2e-backend.log 2>&1) &
BACK=$!
if [ "${E2E_FRONTEND:-dev}" = prod ]; then  # production build (no dev overlay), used for screenshots/Lighthouse
  (cd frontend && NEXT_DIST_DIR=.next-e2e BACKEND_URL=http://localhost:8010 pnpm exec next build >/tmp/calibr-e2e-build.log 2>&1)
  (cd frontend && NEXT_DIST_DIR=.next-e2e BACKEND_URL=http://localhost:8010 pnpm exec next start --port 3005 >/tmp/calibr-e2e-frontend.log 2>&1) &
else
  (cd frontend && NEXT_DIST_DIR=.next-e2e BACKEND_URL=http://localhost:8010 pnpm exec next dev --port 3005 >/tmp/calibr-e2e-frontend.log 2>&1) &
fi
FRONT=$!
trap 'kill $BACK $FRONT 2>/dev/null; pkill -f "uvicorn app.main:app --port 8010"; pkill -f "next (dev|start) --port 3005"; true' EXIT
for i in $(seq 1 60); do curl -sf localhost:8010/api/v1/health >/dev/null && curl -sf localhost:3005/signin >/dev/null && break; sleep 1; done
cd frontend
export E2E_BASE_URL=http://localhost:3005
if [ -n "${STACK_CMD:-}" ]; then eval "$STACK_CMD"; else pnpm exec playwright test "$@"; fi
