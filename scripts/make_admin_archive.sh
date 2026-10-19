#!/usr/bin/env bash
# Builds deploy/seed/admin_archive.sql.gz from the local dev database `calibr` (read-only for `calibr`):
#  1. copies `calibr` into a scratch database `calibr_archive`
#  2. scrubs credentials there (password hashes, sessions, login attempts, reset tokens, jobs)
#  3. writes a data-only, INSERT-based dump (no schema, no alembic_version) that the backend loads on first boot
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=deploy/seed/admin_archive.sql.gz
mkdir -p deploy/seed
dc() { docker compose exec -T db "$@"; }
dc dropdb -U calibr --if-exists calibr_archive
dc createdb -U calibr calibr_archive
dc sh -c 'pg_dump -U calibr -Fc calibr | pg_restore -U calibr -d calibr_archive --no-owner' >/dev/null
dc psql -U calibr -d calibr_archive -v ON_ERROR_STOP=1 -q <<'SQL'
UPDATE users SET password_hash = NULL;
DELETE FROM sessions;
DELETE FROM login_attempts;
DELETE FROM password_resets;
DELETE FROM jobs;
SQL
dc pg_dump -U calibr -d calibr_archive --data-only --column-inserts --rows-per-insert=100 --no-owner --no-privileges \
  --exclude-table=alembic_version --exclude-table-data=sessions --exclude-table-data=login_attempts \
  --exclude-table-data=password_resets --exclude-table-data=jobs | gzip -9 > "$OUT"
REV=$(dc psql -U calibr -d calibr_archive -tAc "select version_num from alembic_version")
echo "$REV" > deploy/seed/admin_archive.revision
dc dropdb -U calibr calibr_archive
echo "wrote $OUT ($(du -h "$OUT" | cut -f1)), schema revision $REV"
