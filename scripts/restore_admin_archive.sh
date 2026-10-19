#!/usr/bin/env bash
# Loads deploy/seed/admin_archive.sql.gz into a database (e.g. a hosted one) from this machine.
# Idempotent: migrates to head, then loads only if the database has no projects yet.
# Use the same ADMIN_EMAIL as the deployed API, then restart the API so it sets that account's password.
#   DATABASE_URL='postgresql://…(Render: External Database URL)' ADMIN_EMAIL=you@example.com scripts/restore_admin_archive.sh
set -euo pipefail
cd "$(dirname "$0")/.."
: "${DATABASE_URL:?set DATABASE_URL to the target database}"
: "${ADMIN_EMAIL:?set ADMIN_EMAIL to the deployed admin email}"
test -f deploy/seed/admin_archive.sql.gz || { echo "deploy/seed/admin_archive.sql.gz missing: run make admin-archive"; exit 1; }
cd backend
uv run alembic upgrade head
uv run python -m scripts.seed_archive --force ../deploy/seed/admin_archive.sql.gz
echo "Done. Restart the API service so the admin password from ADMIN_PASSWORD is applied."
