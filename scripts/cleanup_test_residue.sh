#!/usr/bin/env bash
# Dry run by default; pass --confirm to delete. Uses DATABASE_URL from the environment (never printed beyond host/db).
set -euo pipefail
cd "$(dirname "$0")/../backend"
: "${DATABASE_URL:?set DATABASE_URL to the database to inspect}"
exec uv run python -m scripts.cleanup_test_residue "$@"
