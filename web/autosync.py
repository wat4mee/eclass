"""Opt-in background sync: the student's eClass password, Fernet-encrypted, only while they want it.

Storing and forgetting live here; the password is decrypted only in web/sync.py, at the moment it logs in to eClass
(and by `flask rotate-credentials`, which re-encrypts it under a new key without using it).
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from web import crypto
from web.models import EClassCredential


def enable(db: Session, user_id: int, password: str) -> None:
    """Keep the password (just verified by an eClass login) for background syncs."""
    token, version = crypto.encrypt(password)
    row = db.get(EClassCredential, user_id) or EClassCredential(user_id=user_id)
    row.encrypted_password, row.key_version = token, version
    row.autosync_enabled, row.status, row.last_verified_at = True, "active", datetime.now(timezone.utc)
    db.add(row)


def disable(db: Session, user_id: int, status: str = "active") -> None:
    """Stop background syncs and forget the password at once. status 'invalid': eClass refused it."""
    row = db.get(EClassCredential, user_id)
    if row is None:
        return
    row.encrypted_password = row.key_version = None
    row.autosync_enabled, row.status = False, status


def state(db: Session, user_id: int) -> str:
    """'on', 'off', or 'invalid' (the stored password stopped working and was forgotten)."""
    row = db.get(EClassCredential, user_id)
    if row is None:
        return "off"
    if row.status == "invalid":
        return "invalid"
    return "on" if row.autosync_enabled else "off"
