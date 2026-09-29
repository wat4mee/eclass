"""Encryption of stored secrets, log redaction, and eClass sessions that can never borrow someone else's login."""
import logging

import pytest
from cryptography.fernet import Fernet

from eclass.auth import ConfigError as EClassConfigError
from eclass.auth import EClassClient, SessionExpired
from web import config, crypto, redact


@pytest.fixture
def keys(monkeypatch):
    first, second = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("CREDENTIAL_KEY", first)
    monkeypatch.setenv("CREDENTIAL_KEY_VERSION", "1")
    monkeypatch.delenv("CREDENTIAL_KEY_PREVIOUS", raising=False)
    return first, second


# ---------------------------------------------------------------- encryption

def test_encrypt_and_decrypt_with_the_key_version(keys):
    token, version = crypto.encrypt("s3cret pass")
    assert version == 1 and "s3cret" not in token and crypto.decrypt(token, 1) == "s3cret pass"
    assert crypto.encrypt("s3cret pass")[0] != token  # equal passwords do not look equal when stored


def test_key_rotation_keeps_old_values_readable_until_it_is_finished(keys, monkeypatch):
    first, second = keys
    old_token, _ = crypto.encrypt("old")
    monkeypatch.setenv("CREDENTIAL_KEY", second)
    monkeypatch.setenv("CREDENTIAL_KEY_VERSION", "2")
    monkeypatch.setenv("CREDENTIAL_KEY_PREVIOUS", first)
    new_token, version = crypto.encrypt("new")
    assert version == 2 and crypto.decrypt(old_token, 1) == "old" and crypto.decrypt(new_token, 2) == "new"
    monkeypatch.delenv("CREDENTIAL_KEY_PREVIOUS")  # rotation finished: the old key is gone
    with pytest.raises(crypto.CredentialKeyError):
        crypto.decrypt(old_token, 1)


def test_a_wrong_key_is_an_error_not_garbage(keys, monkeypatch):
    token, _ = crypto.encrypt("x")
    monkeypatch.setenv("CREDENTIAL_KEY", keys[1])
    with pytest.raises(crypto.CredentialKeyError):
        crypto.decrypt(token, 1)


def test_key_settings_are_checked_without_revealing_them(monkeypatch):
    monkeypatch.setenv("HOSTED", "1")
    monkeypatch.delenv("CREDENTIAL_KEY", raising=False)
    with pytest.raises(config.ConfigError, match="CREDENTIAL_KEY is not set"):
        crypto.keys()
    monkeypatch.setenv("CREDENTIAL_KEY", "not-a-real-key-123")
    with pytest.raises(config.ConfigError) as caught:
        crypto.keys()
    assert "not-a-real-key-123" not in str(caught.value)


# ---------------------------------------------------------------- log redaction

@pytest.mark.parametrize("line, secret", [
    ("POST /login username=u2410001&password=hunter2&next=/", "hunter2"),
    ("form: {'username': 'u2410001', 'password': 'hunter2'}", "hunter2"),
    ('{"password": "two words", "user": "x"}', "two words"),
    ("old_password: letmein", "letmein"),
    ("Cookie: MoodleSession=abc123def; path=/", "abc123def"),
    ("Set-Cookie: MoodleSessionIX=zzz999; Secure", "zzz999"),
    ("GET /webservice/rest/server.php?wstoken=tok123abc&wsfunction=x", "tok123abc"),
    ("Authorization: Bearer abcdefgh12345678", "abcdefgh12345678"),
    ("stored gAAAAABmZ1234567890abcdefghijklmnopqrstuv", "gAAAAABmZ1234567890abcdefghijklmnopqrstuv"),
    ("key AIzaSyA1234567890abcdefghijklmnopqrstuvw", "AIzaSyA1234567890abcdefghijklmnopqrstuvw"),
    ("api_key=sk-live-000111222", "sk-live-000111222"),
])
def test_secrets_are_masked(line, secret):
    masked = redact.redact(line)
    assert secret not in masked and redact.MASK in masked


@pytest.mark.parametrize("line", ["user 7 signed in", "sync finished: 3 new materials in 12.5 s",
                                  "GET /course/2539 200", "the compass points north"])
def test_normal_lines_are_left_alone(line):
    assert redact.redact(line) == line


def test_every_log_record_is_redacted(caplog):
    redact.install()
    redact.install()  # idempotent
    caplog.set_level(logging.DEBUG)
    log = logging.getLogger("tests.redaction.child")
    log.info("login with %s", {"password": "p@ss-one"})
    log.warning("header Cookie: MoodleSession=%s", "cookie-two")
    try:
        raise RuntimeError("request failed: https://eclass.inha.ac.kr/x?wstoken=token-three")
    except RuntimeError:
        log.exception("boom")
    logging.getLogger("werkzeug").info('127.0.0.1 "POST /login?password=pw-four HTTP/1.1" 200')
    assert [s for s in ("p@ss-one", "cookie-two", "token-three", "pw-four") if s in caplog.text] == []
    assert caplog.text.count(redact.MASK) >= 4 and "RuntimeError" in caplog.text


# ---------------------------------------------------------------- eClass client

def test_a_saved_session_never_falls_back_to_the_env_login(monkeypatch):
    monkeypatch.setenv("ECLASS_USER", "owner")
    monkeypatch.setenv("ECLASS_PASS", "owner-password")
    client = EClassClient(cookies=[{"name": "MoodleSession", "value": "abc", "domain": "eclass.inha.ac.kr", "path": "/"}])
    assert client.export_cookies()[0]["value"] == "abc"
    with pytest.raises(SessionExpired):  # expired: only the student can log in again
        client.login()
    with pytest.raises(EClassConfigError):  # a student without a password never borrows the .env one
        EClassClient(username="student")


def test_a_forgotten_password_cannot_log_in_again():
    client = EClassClient(username="student", password="pw")
    client.forget_password()
    with pytest.raises(SessionExpired):
        client.login()
