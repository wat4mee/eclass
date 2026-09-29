"""Fixtures for the hosted app: a migrated Postgres test database, every test in a rolled-back transaction.

Needs a local Postgres (Homebrew: `brew services run postgresql@16`, `createdb eclass_web_test`); without it these
tests are skipped and the rest of the suite still runs. TEST_DATABASE_URL selects another test database.
"""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg:///eclass_web_test")


def alembic_config(url: str = TEST_DATABASE_URL) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def engine():
    if "test" not in (make_url(TEST_DATABASE_URL).database or ""):  # the tests drop every table
        pytest.fail("TEST_DATABASE_URL must name a database containing 'test'")
    engine = create_engine(TEST_DATABASE_URL)
    try:
        engine.connect().close()
    except Exception:
        pytest.skip("Postgres test database not reachable (see tests/web/conftest.py)")
    command.downgrade(alembic_config(), "base")  # start from an empty schema
    command.upgrade(alembic_config(), "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    """A session whose work is rolled back after the test; commits inside the test become SAVEPOINT releases."""
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield session
    session.close()
    outer.rollback()
    connection.close()
