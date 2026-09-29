"""Proxy login: a student's eClass username and password are checked by logging in to eClass as them.

The password is used for that one login and then dropped; what is kept is the eClass session cookie, encrypted,
for at most ECLASS_SESSION_MINUTES (EClassSession), so the site can work for the student while they use it.
Nothing here logs a username, password or cookie.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from eclass.auth import ConfigError, EClassClient, EClassError, LoginError
from web import crypto
from web.models import EClassSession

log = logging.getLogger("web.login")


class LoginFailed(Exception):
    """Sign-in failed. reason: 'credentials' (eClass said no) or 'unreachable' (eClass did not answer properly)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def normalize_username(value: str) -> str:
    return (value or "").strip().lower()  # Moodle usernames are lowercase


def check_login(username: str, password: str) -> list[dict]:
    """Log in to eClass as the student; returns the session cookies. Raises LoginFailed."""
    try:
        client = EClassClient(username=username, password=password)
        client.login()
    except (LoginError, ConfigError):  # wrong username or password (or empty ones)
        log.info("eClass sign-in refused")
        raise LoginFailed("credentials") from None
    except EClassError as exc:  # network, timeout, 5xx, unexpected page: not the student's fault
        log.warning("eClass sign-in not possible: %s", exc.code)
        raise LoginFailed("unreachable") from None
    client.forget_password()
    return client.export_cookies()


def save_session(db: Session, user_id: int, cookies: list[dict], minutes: int) -> None:
    token, version = crypto.encrypt(json.dumps(cookies))
    db.merge(EClassSession(user_id=user_id, encrypted_cookie=token, key_version=version,
                           expires_at=datetime.now(timezone.utc) + timedelta(minutes=minutes)))


def load_session(db: Session, user_id: int) -> list[dict] | None:
    """The student's saved eClass cookies, or None when there is no live one (expired ones are deleted)."""
    row = db.get(EClassSession, user_id)
    if row is None:
        return None
    if row.expires_at <= datetime.now(timezone.utc):
        db.delete(row)
        return None
    try:
        return json.loads(crypto.decrypt(row.encrypted_cookie, row.key_version))
    except crypto.CredentialKeyError:  # key rotated without re-encrypting: the student simply signs in again
        db.delete(row)
        return None


def drop_session(db: Session, user_id: int) -> None:
    db.execute(delete(EClassSession).where(EClassSession.user_id == user_id))
