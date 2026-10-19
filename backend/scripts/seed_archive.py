"""Loads the admin archive (deploy/seed/admin_archive.sql.gz) into an empty, migrated database.

Idempotent: does nothing when SEED_ARCHIVE is not "true" or when any project already exists.
Run before the API starts (see deploy/backend.Dockerfile):  python -m scripts.seed_archive
"""

from __future__ import annotations

import gzip
import logging
import os
import sys
from pathlib import Path

import psycopg

from app.core.config import get_settings

log = logging.getLogger("seed_archive")

DEFAULT_PATH = Path(os.environ.get("SEED_ARCHIVE_PATH", "/app/seed/admin_archive.sql.gz"))
# Self-referencing FK: rows of `estimates` are not ordered parent-first in a data-only dump.
SELF_FK = ("estimates", "estimates_parent_estimate_id_fkey",
           "FOREIGN KEY (parent_estimate_id) REFERENCES public.estimates(id) ON DELETE SET NULL")


def _dsn() -> str:
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _tables_in(sql: str) -> list[str]:
    seen: list[str] = []
    for line in sql.splitlines():
        if line.startswith("INSERT INTO public."):
            t = line.split()[2].split(".")[1]
            if t not in seen:
                seen.append(t)
    return seen


def seed(path: Path = DEFAULT_PATH, force: bool = False) -> str:
    if not force and os.environ.get("SEED_ARCHIVE", "").lower() != "true":
        return "skipped: SEED_ARCHIVE is not true"
    if not path.exists():
        return f"skipped: {path} not found"
    with psycopg.connect(_dsn()) as conn:
        if conn.execute("SELECT EXISTS (SELECT 1 FROM projects)").fetchone()[0]:
            return "skipped: database already has projects"
        sql = gzip.decompress(path.read_bytes()).decode()
        # Recent pg_dump versions wrap the dump in psql-only meta-commands (\restrict … \unrestrict).
        sql = "\n".join(line for line in sql.splitlines() if not line.startswith("\\"))
        tables = _tables_in(sql)
        with conn.transaction():
            # Only rows created by migrations/previous boots (reference data, a bootstrap admin) can exist here.
            conn.execute("TRUNCATE " + ", ".join(f"public.{t}" for t in tables) + " CASCADE")
            conn.execute(f"ALTER TABLE public.{SELF_FK[0]} DROP CONSTRAINT IF EXISTS {SELF_FK[1]}")
            conn.execute(sql)
            conn.execute(f"ALTER TABLE public.{SELF_FK[0]} ADD CONSTRAINT {SELF_FK[1]} {SELF_FK[2]}")
            conn.execute("SELECT pg_catalog.set_config('search_path', 'public', false)")
            admin_email = get_settings().admin_email.strip().lower()
            if admin_email:
                # The archive's owner becomes this deployment's admin; bootstrap then sets its password.
                conn.execute(
                    """UPDATE users SET email = %s
                       WHERE id = (SELECT id FROM users WHERE role = 'admin' AND NOT archived ORDER BY created_at LIMIT 1)
                         AND NOT EXISTS (SELECT 1 FROM users WHERE email = %s)""",
                    (admin_email, admin_email),
                )
        counts = {t: conn.execute(f"SELECT count(*) FROM public.{t}").fetchone()[0] for t in ("projects", "tasks", "users")}
    return f"seeded {len(tables)} tables: {counts}"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    args = sys.argv[1:]
    force = "--force" in args
    paths = [a for a in args if not a.startswith("--")]
    print(seed(Path(paths[0]) if paths else DEFAULT_PATH, force=force))
