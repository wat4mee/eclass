"""Milestone 4: opt-in background sync with a stored, encrypted password; the scheduled run; key rotation.

eClass is always faked; the "stored password" is FakeEClass.PASSWORD, never a real one.
"""
import logging
import os
import re
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, text

from eclass.auth import LoginError, NetworkError
from web import autosync, crypto, sync
from web.models import Base, EClassCredential, EClassSession, SyncRun, User
from tests.web.conftest import FakeEClass, csrf_token, sign_in
from tests.web.fake_eclass import FakeSite
from tests.web.test_dashboard import material_id


class PasswordSite(FakeSite):
    """The fake eClass reached by logging in with a username and password (what the background sync does)."""
    logins: list[str] = []

    def __init__(self, username=None, password=None, cookies=None, **kwargs):
        super().__init__(**kwargs)
        self.username, self.password = username, password

    def login(self):
        PasswordSite.logins.append(self.username)
        if self.username.startswith("u-offline"):
            raise NetworkError("ConnectionError: /login.php")
        if self.password != FakeEClass.PASSWORD:
            raise LoginError("login failed (redirected back to login page)")
        return True

    def forget_password(self):
        self.password = None

    def export_cookies(self):
        return [{"name": "MoodleSession", "value": "session-from-stored-password", "domain": "eclass.inha.ac.kr",
                 "path": "/"}]


@pytest.fixture(autouse=True)
def fake_password_login(monkeypatch):
    PasswordSite.logins = []
    monkeypatch.setattr(sync, "EClassClient", PasswordSite)


def keep_signed_in(client, username="u2410001", password=FakeEClass.PASSWORD):
    """Sign in with "keep me synced in the background" ticked."""
    return client.post("/login", data={"username": username, "password": password, "keep": "y",
                                       "csrf_token": csrf_token(client)})


def user_id(app, username="u2410001") -> int:
    with app.extensions["db_sessions"]() as db:
        return db.scalar(select(User.id).where(User.eclass_username == username))


def credential(app, uid) -> EClassCredential | None:
    with app.extensions["db_sessions"]() as db:
        return db.get(EClassCredential, uid)


def run_all(app):
    slept = []
    summary = sync.run_all(app.extensions["db_engine"], app.extensions["db_sessions"], pause=1, sleep=slept.append)
    return summary, slept


def english(client):
    client.get("/login?lang=en")


# ---------------------------------------------------------------- opting in and out

def test_background_sync_is_off_unless_the_box_is_ticked(client, app):
    html = client.get("/login?lang=en").get_data(as_text=True)
    box = re.search(r'<input type="checkbox" name="keep"[^>]*>', html).group(0)
    assert "checked" not in box and "Keep me synced in the background" in html
    sign_in(client)
    assert credential(app, user_id(app)) is None


def test_ticking_the_box_stores_the_password_encrypted(client, app, engine, caplog):
    caplog.set_level(logging.DEBUG)
    assert keep_signed_in(client).status_code == 302
    cred = credential(app, user_id(app))
    assert cred.autosync_enabled and cred.status == "active" and cred.key_version == 1
    assert FakeEClass.PASSWORD not in cred.encrypted_password
    assert crypto.decrypt(cred.encrypted_password, cred.key_version) == FakeEClass.PASSWORD
    with engine.connect() as connection:  # nowhere in the database in plain text, nor in the logs
        dump = " ".join(connection.execute(text(
            f"SELECT coalesce(string_agg(to_jsonb(t)::text, ' '), '') FROM {table.name} t")).scalar()
            for table in Base.metadata.sorted_tables)
    assert FakeEClass.PASSWORD not in dump and FakeEClass.PASSWORD not in caplog.text


def test_turning_it_off_deletes_the_password_at_once(client, app):
    english(client)
    keep_signed_in(client)
    resp = client.post("/account/autosync/off", data={"csrf_token": csrf_token(client, "/account")})
    assert resp.status_code == 302
    cred = credential(app, user_id(app))
    assert cred.encrypted_password is None and cred.key_version is None and not cred.autosync_enabled
    assert "Background sync is off and your password is deleted." in client.get("/account").get_data(as_text=True)


def test_turning_it_on_needs_the_right_password(client, app):
    sign_in(client)
    token = csrf_token(client, "/account")
    assert client.post("/account/autosync", data={"password": "wrong", "csrf_token": token}).status_code == 401
    assert credential(app, user_id(app)) is None
    resp = client.post("/account/autosync", data={"password": FakeEClass.PASSWORD, "csrf_token": token})
    assert resp.status_code == 302 and credential(app, user_id(app)).autosync_enabled
    assert client.post("/account/autosync/off").status_code == 400  # CSRF


def test_signing_in_again_refreshes_a_stored_password(client, app):
    keep_signed_in(client)
    before = credential(app, user_id(app)).encrypted_password
    sign_in(app.test_client())  # box not ticked, but background sync is on: the stored copy is replaced
    after = credential(app, user_id(app))
    assert after.autosync_enabled and after.encrypted_password != before


def test_passwords_are_decrypted_only_by_the_sync():
    """The spec: decrypt only inside the sync code path (plus the rotation command, which only re-encrypts)."""
    web = Path(__file__).resolve().parents[2] / "web"
    users = sorted(str(p.relative_to(web)) for p in web.rglob("*.py")
                   if re.search(r"decrypt\([^)]*encrypted_password", p.read_text()))
    assert users == ["crypto.py", "sync.py"]


# ---------------------------------------------------------------- the scheduled run

def test_scheduled_run_syncs_only_students_who_opted_in(client, app):
    keep_signed_in(client, "u2410001")
    sign_in(app.test_client(), "u2410002")
    summary, _ = run_all(app)
    assert summary == {"students": 1, "done": 1, "failed": 0, "busy": 0, "stopped": False}
    with app.extensions["db_sessions"]() as db:
        runs = db.scalars(select(SyncRun).where(SyncRun.trigger == "schedule")).all()
        assert [(r.user_id, r.status) for r in runs] == [(user_id(app), "done")]
    assert PasswordSite.logins == ["u2410001"]


def test_one_broken_student_does_not_stop_the_others(client, app):
    keep_signed_in(client, "u2410001")
    keep_signed_in(app.test_client(), "u2410002")
    with app.extensions["db_sessions"]() as db:  # the first student changed their password on eClass
        autosync.enable(db, user_id(app, "u2410001"), "old-password-no-longer-valid")
        db.commit()
    summary, slept = run_all(app)
    assert (summary["done"], summary["failed"], summary["stopped"]) == (1, 1, False)
    broken = credential(app, user_id(app, "u2410001"))
    assert broken.status == "invalid" and broken.encrypted_password is None and not broken.autosync_enabled
    assert slept == [1]  # a refused password is not an outage: the normal pause
    summary, _ = run_all(app)  # the next run does not try the refused password again (no account lockout)
    assert summary["students"] == 1 and PasswordSite.logins.count("u2410001") == 1


def test_an_eclass_outage_stops_the_run_with_growing_pauses(app):
    for n in range(4):
        keep_signed_in(app.test_client(), f"u-offline{n}")
    summary, slept = run_all(app)
    assert summary == {"students": 4, "done": 0, "failed": 3, "busy": 0, "stopped": True}
    assert slept == [2, 4]
    assert all(credential(app, user_id(app, f"u-offline{n}")).status == "active" for n in range(4))


def test_a_scheduled_run_keeps_no_eclass_session(client, app):
    keep_signed_in(client)
    uid = user_id(app)
    with app.extensions["db_sessions"]() as db:
        db.execute(EClassSession.__table__.delete())
        db.commit()
    run_all(app)
    with app.extensions["db_sessions"]() as db:
        assert db.get(EClassSession, uid) is None


def test_a_refused_password_is_explained_on_the_home_page(client, app):
    english(client)
    keep_signed_in(client)
    with app.extensions["db_sessions"]() as db:
        autosync.enable(db, user_id(app), "old-password-no-longer-valid")
        db.commit()
    run_all(app)
    assert "eClass no longer accepts your stored password" in client.get("/").get_data(as_text=True)
    assert 'name="keep" value="y" checked' in client.get("/reconnect").get_data(as_text=True)


def test_the_command_needs_something_to_do():
    with pytest.raises(SystemExit):
        sync.main(["--packs", "0"])


# ---------------------------------------------------------------- the website uses the stored password

def test_refresh_and_files_work_after_the_session_ended(client, app):
    keep_signed_in(client)
    uid = user_id(app)
    sync.sync_user(app.extensions["db_engine"], app.extensions["db_sessions"], uid, "login", FakeSite())
    with app.extensions["db_sessions"]() as db:
        db.execute(EClassSession.__table__.delete())
        db.commit()
    resp = client.post("/sync", data={"csrf_token": csrf_token(client, "/")})
    assert resp.headers["Location"] == "/" and app.config["STARTED_SYNCS"][-1] == (uid, "button")
    resp = client.get(f"/file/{material_id(app)}")
    assert resp.status_code == 200 and resp.data.startswith(b"%PDF")
    with app.extensions["db_sessions"]() as db:
        assert db.get(EClassSession, uid) is not None  # the new session is kept for the next clicks


# ---------------------------------------------------------------- key rotation

def test_rotation_re_encrypts_every_secret_under_the_new_key(client, app, monkeypatch):
    keep_signed_in(client)
    uid = user_id(app)
    monkeypatch.setenv("CREDENTIAL_KEY_PREVIOUS", os.environ["CREDENTIAL_KEY"])
    monkeypatch.setenv("CREDENTIAL_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CREDENTIAL_KEY_VERSION", "2")
    result = app.test_cli_runner().invoke(args=["rotate-credentials"])
    assert "re-encrypted 1 password(s) and 1 session(s); dropped 0" in result.output
    monkeypatch.delenv("CREDENTIAL_KEY_PREVIOUS")  # the old key is gone: everything must open with the new one
    cred = credential(app, uid)
    assert cred.key_version == 2 and crypto.decrypt(cred.encrypted_password, 2) == FakeEClass.PASSWORD
    with app.extensions["db_sessions"]() as db:
        saved = db.get(EClassSession, uid)
        assert saved.key_version == 2 and "MoodleSession" in crypto.decrypt(saved.encrypted_cookie, 2)


def test_rotation_drops_what_no_key_can_open(client, app, monkeypatch):
    keep_signed_in(client)
    uid = user_id(app)
    monkeypatch.setenv("CREDENTIAL_KEY", Fernet.generate_key().decode())  # the old key was lost
    monkeypatch.setenv("CREDENTIAL_KEY_VERSION", "2")
    result = app.test_cli_runner().invoke(args=["rotate-credentials"])
    assert "dropped 2" in result.output
    cred = credential(app, uid)
    assert cred.status == "invalid" and cred.encrypted_password is None
    with app.extensions["db_sessions"]() as db:
        assert db.get(EClassSession, uid) is None
