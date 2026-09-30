"""Encryption of stored eClass secrets (passwords of students who opted into background sync, and short-lived
eClass session cookies) with Fernet.

The key exists only in environment variables, never in the repository or the database:
    CREDENTIAL_KEY            the current key (generate: see README, "CREDENTIAL_KEY")
    CREDENTIAL_KEY_VERSION    its number, stored next to every encrypted value (default 1)
    CREDENTIAL_KEY_PREVIOUS   the key before the last rotation (version - 1), kept until `flask rotate-credentials`
                              has re-encrypted every row
Decrypt only at the moment a secret is used.
"""
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

from web.config import ConfigError, hosted

log = logging.getLogger("web.crypto")
_temporary_key = None  # local development without CREDENTIAL_KEY: one random key per process


class CredentialKeyError(RuntimeError):
    """A stored secret cannot be decrypted (unknown key version or wrong key)."""


def _fernet(key: str, name: str) -> Fernet:
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise ConfigError(f"{name} is not a valid Fernet key") from None  # never echo the value


def keys() -> tuple[int, dict[int, Fernet]]:
    """(current version, {version: Fernet}) from the environment."""
    global _temporary_key
    try:
        version = int(os.getenv("CREDENTIAL_KEY_VERSION", "1"))
    except ValueError:
        raise ConfigError("CREDENTIAL_KEY_VERSION must be a whole number") from None
    current = os.getenv("CREDENTIAL_KEY")
    if not current:
        if hosted():
            raise ConfigError("CREDENTIAL_KEY is not set")
        if _temporary_key is None:
            _temporary_key = Fernet.generate_key().decode()
            log.warning("CREDENTIAL_KEY is not set: using a temporary key; saved eClass sessions end on restart")
        current = _temporary_key
    found = {version: _fernet(current, "CREDENTIAL_KEY")}
    previous = os.getenv("CREDENTIAL_KEY_PREVIOUS")
    if previous:
        found[version - 1] = _fernet(previous, "CREDENTIAL_KEY_PREVIOUS")
    return version, found


def encrypt(plaintext: str) -> tuple[str, int]:
    """(token, key_version): store both."""
    version, found = keys()
    return found[version].encrypt(plaintext.encode()).decode(), version


def decrypt(token: str, key_version: int) -> str:
    _, found = keys()
    fernet = found.get(key_version)
    if fernet is None:
        raise CredentialKeyError(f"no key for version {key_version}")
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        raise CredentialKeyError(f"stored secret does not match key version {key_version}") from None


def rotate(db) -> dict:
    """Re-encrypt every stored secret under the current key (`flask --app web rotate-credentials`).

    Run it after setting the new CREDENTIAL_KEY with CREDENTIAL_KEY_VERSION + 1 and the old key as
    CREDENTIAL_KEY_PREVIOUS; afterwards CREDENTIAL_KEY_PREVIOUS can be removed. A secret no key can decrypt is
    dropped: a password is forgotten (background sync stops until the student enters it again), a session ends.
    The values are only re-encrypted here, never used.
    """
    from sqlalchemy import select

    from web.models import EClassCredential, EClassSession
    version, _ = keys()
    stats = {"passwords": 0, "sessions": 0, "dropped": 0}
    for row in db.scalars(select(EClassCredential).where(EClassCredential.key_version != version)):
        try:
            row.encrypted_password, row.key_version = encrypt(decrypt(row.encrypted_password, row.key_version))
            stats["passwords"] += 1
        except CredentialKeyError:
            row.encrypted_password = row.key_version = None
            row.autosync_enabled, row.status = False, "invalid"
            stats["dropped"] += 1
    for row in db.scalars(select(EClassSession).where(EClassSession.key_version != version)):
        try:
            row.encrypted_cookie, row.key_version = encrypt(decrypt(row.encrypted_cookie, row.key_version))
            stats["sessions"] += 1
        except CredentialKeyError:
            db.delete(row)
            stats["dropped"] += 1
    return stats
