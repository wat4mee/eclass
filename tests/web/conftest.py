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


class FakeEClass:
    """Stands in for eclass.auth.EClassClient: tests never reach eClass and never use real credentials."""
    PASSWORD = "correct horse battery"
    COOKIE = "fake-moodle-session-7f3a9c"

    def __init__(self, username=None, password=None, cookies=None):
        self.username, self.password = username, password

    def login(self):
        from eclass.auth import LoginError, NetworkError
        if self.username == "u-offline":
            raise NetworkError("ConnectionError: /login.php")
        if self.username == "u-crash":
            raise RuntimeError(f"unexpected page while logging in with password={self.password}")
        if self.password != self.PASSWORD:
            raise LoginError("login failed (redirected back to login page)")
        return True

    def forget_password(self):
        self.password = None

    def export_cookies(self):
        return [{"name": "MoodleSession", "value": self.COOKIE, "domain": "eclass.inha.ac.kr", "path": "/"}]

    def get(self, url, stream=False):  # /file/<id> streams through the student's session
        from tests.web.fake_eclass import FakeResponse
        if url.endswith(".html"):
            return FakeResponse(url, b"<script>alert(1)</script>", "text/html")
        return FakeResponse(url, b"%PDF-1.4 fake file", "application/pdf")


@pytest.fixture
def app(engine, monkeypatch):
    """The hosted app on the test database, with a fake eClass and a fresh encryption key."""
    from cryptography.fernet import Fernet
    from sqlalchemy import text

    import web
    from web import eclass_login, tasks
    from web.extensions import limiter

    monkeypatch.setenv("CREDENTIAL_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("CREDENTIAL_KEY_PREVIOUS", raising=False)
    monkeypatch.delenv("CREDENTIAL_KEY_VERSION", raising=False)
    monkeypatch.setattr(eclass_login, "EClassClient", FakeEClass)
    syncs = []  # background syncs are recorded, not run: sync tests call web.sync.sync_user directly
    monkeypatch.setattr(tasks, "start_sync", lambda app, user_id, trigger: syncs.append((user_id, trigger)))
    app = web.create_app({"DATABASE_URL": TEST_DATABASE_URL, "TESTING": True, "SECRET_KEY": "test-secret"})
    app.config["STARTED_SYNCS"] = syncs
    limiter.reset()
    yield app
    app.extensions["db_engine"].dispose()  # close this app's pooled connections
    with engine.begin() as connection:  # the app commits for real: empty every table after the test
        connection.execute(text("TRUNCATE users, courses RESTART IDENTITY CASCADE"))
    limiter.reset()


@pytest.fixture
def client(app):
    return app.test_client()


def csrf_token(client, path="/login") -> str:
    import re
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def sign_in(client, username="u2410001", password=FakeEClass.PASSWORD):
    return client.post("/login", data={"username": username, "password": password, "csrf_token": csrf_token(client)})


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
