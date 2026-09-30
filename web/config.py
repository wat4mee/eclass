"""Settings of the hosted app, from environment variables (Render) or .env (local development).

HOSTED=1 (set on Render) makes every secret mandatory; locally the app starts with safe development defaults.
Error messages name a missing setting, never a value.
"""
import os
import secrets
from datetime import timedelta
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


def _list(name: str, default: str) -> list[str]:
    return [item.strip().lower() for item in os.getenv(name, default).split(",") if item.strip()]


def allowed_hosts() -> list[str]:
    """Host names the site answers to: ALLOWED_HOSTS (e.g. a custom domain) plus, on Render, the service's own
    onrender.com name, which Render provides as RENDER_EXTERNAL_HOSTNAME."""
    hosts = _list("ALLOWED_HOSTS", "" if hosted() else "localhost,127.0.0.1")
    render = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip().lower()
    return hosts + [render] if render and render not in hosts else hosts


def from_env() -> dict:
    """Flask config for create_app()."""
    secure = hosted() or os.getenv("COOKIE_SECURE") == "1"  # HTTPS-only cookies; off only for local http
    return {
        "APP_NAME": os.getenv("APP_NAME", "sclass"),
        "SECRET_KEY": secret_key(),
        "DATABASE_URL": database_url(),
        "HOSTED": hosted(),
        # requests with another Host header are refused (DNS rebinding, misrouted traffic)
        "ALLOWED_HOSTS": allowed_hosts(),
        # the client IP for rate limits: on Render (RENDER is set) the first X-Forwarded-For entry; elsewhere the
        # entry PROXY_HOPS from the end
        "BEHIND_RENDER": bool(os.getenv("RENDER")),
        "PROXY_HOPS": int(os.getenv("PROXY_HOPS", "1")),
        # cookies: HTTPS only, invisible to JavaScript, not sent on cross-site requests
        "SESSION_COOKIE_NAME": "sclass_session",
        "SESSION_COOKIE_SECURE": secure, "SESSION_COOKIE_HTTPONLY": True, "SESSION_COOKIE_SAMESITE": "Lax",
        "REMEMBER_COOKIE_SECURE": secure, "REMEMBER_COOKIE_HTTPONLY": True, "REMEMBER_COOKIE_SAMESITE": "Lax",
        "REMEMBER_COOKIE_DURATION": timedelta(days=14),
        "PERMANENT_SESSION_LIFETIME": timedelta(days=14),
        "WTF_CSRF_TIME_LIMIT": None,  # a CSRF token is valid for the whole session
        # login rate limits: per IP (campus Wi-Fi shares one IP, so not too low) and per eClass username
        "RATELIMIT_STORAGE_URI": os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
        "LOGIN_LIMIT_IP": os.getenv("LOGIN_LIMIT_IP", "10 per minute;60 per hour"),
        "LOGIN_LIMIT_USER": os.getenv("LOGIN_LIMIT_USER", "5 per 15 minutes"),
        "ECLASS_SESSION_MINUTES": int(os.getenv("ECLASS_SESSION_MINUTES", "120")),  # saved eClass session lifetime
        "AI_DAILY_LIMIT": int(os.getenv("AI_DAILY_LIMIT", "30")),  # chat questions per student per day (shared quota)
        # bearer token for POST /internal/sync-all (the free scheduler: GitHub Actions); empty = endpoint off
        "CRON_SECRET": os.getenv("CRON_SECRET", "").strip(),
    }
