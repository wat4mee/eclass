"""Milestone 2: proxy sign-in, sessions, deletion and the security requirements (eClass is always faked)."""
import json
import logging
import re

import pytest
from flask import request
from sqlalchemy import select, text

from web import crypto
from web.models import Base, Course, EClassSession, Enrollment, User
from tests.web.conftest import FakeEClass, csrf_token, sign_in

WRONG = "hunter2-wrong-password"


def rows(app, model, **where):
    with app.extensions["db_sessions"]() as db:
        return db.scalars(select(model).filter_by(**where)).all()


def english(client):
    client.get("/login?lang=en")  # sets the language cookie for the following requests


# ---------------------------------------------------------------- sign-in

def test_login_page_is_our_own_brand_and_says_unofficial(client):
    html = client.get("/login?lang=en").get_data(as_text=True)
    assert "Unofficial student project, not affiliated with INHA University." in html
    assert "sclass" in html
    assert "Norasmiy talaba loyihasi" in client.get("/login?lang=uz").get_data(as_text=True)
    assert "Неофициальный студенческий проект" in client.get("/login?lang=ru").get_data(as_text=True)


def test_sign_in_creates_the_user_and_a_short_encrypted_eclass_session(client, app):
    resp = sign_in(client, username="  U2410001 ")
    assert resp.status_code == 302 and resp.headers["Location"] == "/"
    [user] = rows(app, User)
    assert user.eclass_username == "u2410001" and user.last_login_at is not None
    [saved] = rows(app, EClassSession, user_id=user.id)
    assert FakeEClass.COOKIE not in saved.encrypted_cookie
    cookies = json.loads(crypto.decrypt(saved.encrypted_cookie, saved.key_version))
    assert cookies == [{"name": "MoodleSession", "value": FakeEClass.COOKIE, "domain": "eclass.inha.ac.kr", "path": "/"}]
    assert 119 <= (saved.expires_at - saved.created_at).total_seconds() / 60 <= 121
    assert "u2410001" in client.get("/").get_data(as_text=True)


def test_wrong_password_and_unknown_user_get_the_same_answer(client, app):
    english(client)
    answers = [sign_in(client, name, WRONG) for name in ("u2410001", "nobody")]
    assert [a.status_code for a in answers] == [401, 401]
    for answer in answers:
        assert "Sign-in failed. Check your eClass username and password." in answer.get_data(as_text=True)
    assert rows(app, User) == []


def test_eclass_being_down_is_not_blamed_on_the_student(client):
    english(client)
    resp = sign_in(client, "u-offline", "whatever")
    assert resp.status_code == 503 and "eClass is not responding right now" in resp.get_data(as_text=True)


def test_passwords_and_cookies_are_never_stored_or_logged(client, app, engine, caplog):
    caplog.set_level(logging.DEBUG)
    app.config["PROPAGATE_EXCEPTIONS"] = False  # a crash is handled and logged as in production
    sign_in(client, "u2410001", WRONG)
    sign_in(client, "u2410001", FakeEClass.PASSWORD)
    assert sign_in(app.test_client(), "u-crash", "crash-secret-99").status_code == 500
    secrets = (WRONG, FakeEClass.PASSWORD, "crash-secret-99", FakeEClass.COOKIE)
    logged = caplog.text
    assert "server error on /login" in logged and "[REDACTED]" in logged  # the crash was logged, masked
    assert not [s for s in secrets if s in logged]
    with engine.connect() as connection:
        dump = " ".join(connection.execute(text(
            f"SELECT coalesce(string_agg(to_jsonb(t)::text, ' '), '') FROM {table.name} t")).scalar()
            for table in Base.metadata.sorted_tables)
    assert not [s for s in secrets if s in dump]


# ---------------------------------------------------------------- CSRF, rate limits, cookies, headers

def test_every_form_needs_its_csrf_token(client):
    assert client.post("/login", data={"username": "u2410001", "password": FakeEClass.PASSWORD}).status_code == 400
    sign_in(client)
    assert client.post("/logout").status_code == 400
    assert client.post("/account/delete", data={"confirm": "y"}).status_code == 400
    assert client.post("/account/delete", data={"confirm": "y", "csrf_token": "forged"}).status_code == 400
    assert client.get("/").status_code == 200  # still signed in, nothing deleted


def test_sign_in_is_limited_per_username(client):
    assert [sign_in(client, "u2410001", WRONG).status_code for _ in range(5)] == [401] * 5
    resp = sign_in(client, "u2410001", WRONG)
    assert resp.status_code == 429 and "Urinishlar juda ko" in resp.get_data(as_text=True)


def test_sign_in_is_limited_per_ip(client):
    codes = [sign_in(client, f"u24100{n:02d}", WRONG).status_code for n in range(11)]
    assert codes == [401] * 10 + [429]


def test_cookies_are_secure_http_only_and_same_site(app):
    app.config.update(SESSION_COOKIE_SECURE=True, REMEMBER_COOKIE_SECURE=True)
    client = app.test_client()
    html = client.get("/login", base_url="https://localhost").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    resp = client.post("/login", base_url="https://localhost", headers={"Referer": "https://localhost/login"},
                       data={"username": "u2410001", "password": FakeEClass.PASSWORD, "csrf_token": token})
    assert resp.status_code == 302  # over HTTPS, CSRF also requires a same-site Referer (browsers send it)
    cookies = resp.headers.getlist("Set-Cookie")
    for name in ("sclass_session=", "remember_token="):
        cookie = next(c for c in cookies if c.startswith(name))
        assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie, cookie


def test_security_headers(client):
    headers = client.get("/login").headers
    policy = headers["Content-Security-Policy"]
    directives = dict(d.strip().split(" ", 1) for d in policy.split(";"))
    assert directives["script-src"] == "'self'" and directives["frame-ancestors"] == "'none'"  # no inline scripts
    assert [d for d, v in directives.items() if "unsafe" in v] == ["style-src-attr"]  # only KaTeX's style attributes
    assert headers["X-Frame-Options"] == "DENY" and headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "same-origin"


def test_other_hosts_are_refused_but_the_health_check_answers(client):
    assert client.get("/login", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/healthz", headers={"Host": "render-internal-check"}).status_code == 200


@pytest.fixture
def on_render(monkeypatch, engine):
    """The app as Render runs it: HOSTED=1, behind Render's proxies, reached as sclass.onrender.com."""
    import web
    from cryptography.fernet import Fernet
    from tests.web.conftest import TEST_DATABASE_URL
    for name, value in {"HOSTED": "1", "RENDER": "true", "RENDER_EXTERNAL_HOSTNAME": "sclass.onrender.com",
                        "CREDENTIAL_KEY": Fernet.generate_key().decode(), "SECRET_KEY": "render-test",
                        "DATABASE_URL": TEST_DATABASE_URL}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    app = web.create_app()
    app.add_url_rule("/_whoami", "whoami", lambda: request.remote_addr)
    yield app.test_client()
    app.extensions["db_engine"].dispose()


def test_on_render_the_own_hostname_is_allowed_and_nothing_else(on_render):
    https = {"base_url": "https://sclass.onrender.com"}
    assert on_render.get("/login", **https).status_code == 200
    assert on_render.get("/login", base_url="https://localhost").status_code == 400
    assert "max-age" in on_render.get("/login", **https).headers["Strict-Transport-Security"]


def test_on_render_the_client_ip_is_the_first_forwarded_one(on_render):
    """Render puts the student's IP first, then its proxies: rate limits must count the student, not a proxy."""
    resp = on_render.get("/_whoami", base_url="https://sclass.onrender.com",
                         headers={"X-Forwarded-For": "203.0.113.7, 104.16.0.1, 10.10.0.5"})
    assert resp.get_data(as_text=True) == "203.0.113.7"


# ---------------------------------------------------------------- sessions

@pytest.mark.parametrize("path", ["/", "/account"])
def test_pages_need_sign_in(client, path):
    resp = client.get(path)
    assert resp.status_code == 302 and resp.headers["Location"].startswith("/login")


def test_sign_out_ends_the_site_session_and_the_eclass_session(client, app):
    sign_in(client)
    resp = client.post("/logout", data={"csrf_token": csrf_token(client, "/account")})
    assert resp.status_code == 302 and resp.headers["Location"] == "/login"
    assert rows(app, EClassSession) == []
    assert client.get("/").status_code == 302


def test_a_deleted_user_is_signed_out(client, engine):
    sign_in(client)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    assert client.get("/").status_code == 302


# ---------------------------------------------------------------- delete my data, privacy

def test_deleting_needs_the_confirmation_box(client, app):
    sign_in(client)
    resp = client.post("/account/delete", data={"csrf_token": csrf_token(client, "/account")})
    assert resp.status_code == 400 and len(rows(app, User)) == 1


def test_delete_my_data_removes_everything_personal(client, app):
    english(client)
    sign_in(client, "u2410001")
    other = app.test_client()
    sign_in(other, "u2410002")
    with app.extensions["db_sessions"]() as db:
        ids = {u.eclass_username: u.id for u in db.scalars(select(User))}
        db.add_all([Course(id=2539, name="Calculus 1"), Course(id=2562, name="OOP 1")])
        db.commit()
        db.add_all([Enrollment(user_id=ids["u2410001"], course_id=2539),  # nobody else takes this course
                    Enrollment(user_id=ids["u2410001"], course_id=2562),
                    Enrollment(user_id=ids["u2410002"], course_id=2562)])
        db.commit()
    resp = client.post("/account/delete", data={"confirm": "y", "csrf_token": csrf_token(client, "/account")})
    assert resp.status_code == 302 and resp.headers["Location"] == "/login"
    assert "Your account and data are deleted." in client.get("/login").get_data(as_text=True)
    assert [u.eclass_username for u in rows(app, User)] == ["u2410002"]
    assert rows(app, EClassSession, user_id=ids["u2410001"]) == []
    assert [c.id for c in rows(app, Course)] == [2562]
    assert client.get("/").status_code == 302 and other.get("/").status_code == 200


@pytest.mark.parametrize("lang, words", [
    ("en", ["Fernet", "Gemini", "2 hours", "Disconnect &amp; delete my data", "not affiliated with INHA University"]),
    ("uz", ["Fernet", "Gemini", "2 soat", "INHA University"]),
    ("ru", ["Fernet", "Gemini", "2 часов", "INHA University"]),
])
def test_privacy_page_is_public_and_plain(client, lang, words):
    resp = client.get(f"/privacy?lang={lang}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert [w for w in words if w not in html] == []
