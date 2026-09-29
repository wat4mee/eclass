"""Settings of the hosted app, from environment variables (Render) or .env (local development).

HOSTED=1 (set on Render) makes every secret mandatory; locally the app starts with safe development defaults.
Error messages name a missing setting, never a value.
"""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

LOCAL_DATABASE_URL = "postgresql+psycopg:///eclass_web_dev"  # Homebrew Postgres on this Mac


class ConfigError(RuntimeError):
    """A required setting is missing or malformed."""


def hosted() -> bool:
    return os.getenv("HOSTED") == "1"


def database_url(url: str | None = None) -> str:
    """SQLAlchemy URL for psycopg 3. Neon and Render hand out postgres:// or postgresql:// URLs."""
    url = url or os.getenv("DATABASE_URL")
    if not url:
        if hosted():
            raise ConfigError("DATABASE_URL is not set")
        return LOCAL_DATABASE_URL
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def secret_key() -> str:
    key = os.getenv("SECRET_KEY")
    if key:
        return key
    if hosted():
        raise ConfigError("SECRET_KEY is not set")
    return secrets.token_hex(32)  # local development only: everyone is logged out when the server restarts


def from_env() -> dict:
    """Flask config for create_app()."""
    return {
        "APP_NAME": os.getenv("APP_NAME", "Study Companion"),
        "SECRET_KEY": secret_key(),
        "DATABASE_URL": database_url(),
        "HOSTED": hosted(),
    }
