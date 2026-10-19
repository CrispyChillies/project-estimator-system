"""Deployment helpers: hosted DATABASE_URL normalisation and the idempotent archive seed."""

import gzip

from app.core.config import Settings
from scripts import seed_archive


def test_hosted_database_urls_use_psycopg_driver():
    for url in ("postgres://u:p@h:5432/d", "postgresql://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"):
        assert Settings(database_url=url).database_url == "postgresql+psycopg://u:p@h:5432/d"


def test_seed_is_opt_in_and_never_overwrites(db, monkeypatch, tmp_path):
    monkeypatch.delenv("SEED_ARCHIVE", raising=False)
    assert seed_archive.seed(tmp_path / "missing.sql.gz").startswith("skipped: SEED_ARCHIVE")
    seed_file = tmp_path / "archive.sql.gz"
    seed_file.write_bytes(gzip.compress(b"SELECT 1;"))
    from app.db.models import Project

    db.add(Project(name="existing", client_name="", domain="", tech_tags=[], description="", status="draft",
                   data_source="user"))
    db.commit()
    assert seed_archive.seed(seed_file, force=True) == "skipped: database already has projects"


def test_seed_table_discovery():
    sql = "SET x = 1;\nINSERT INTO public.users (id) VALUES\n(1);\nINSERT INTO public.projects (id) VALUES (2);\n"
    assert seed_archive._tables_in(sql) == ["users", "projects"]
