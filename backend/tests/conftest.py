import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TEST_DB = os.environ.get("TEST_DATABASE_URL")
os.environ["LLM_MODE"] = "fake"
if TEST_DB:
    os.environ["DATABASE_URL"] = TEST_DB


def _prepare_db() -> None:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    url = make_url(TEST_DB)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        if not c.execute(text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": url.database}).scalar():
            c.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.upgrade(cfg, "head")


_prepared = False


@pytest.fixture
def db():
    global _prepared
    if not TEST_DB:
        pytest.skip("TEST_DATABASE_URL not set (run `make test`)")
    if not _prepared:
        _prepare_db()
        _prepared = True
    from sqlalchemy import text

    from app.db.base import Base
    from app.db.session import SessionLocal, engine
    from app.services.reference import ensure_reference_data

    with engine.begin() as c:
        names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        c.execute(text(f"TRUNCATE {names} CASCADE"))
    s = SessionLocal()
    ensure_reference_data(s)
    yield s
    s.close()
