"""Endpoints for machines, not students: the free scheduler (GitHub Actions, .github/workflows/sync-cron.yml)
starts the background sync of every opted-in student here.

No login and no CSRF token (nothing here relies on cookies): the caller proves itself with
`Authorization: Bearer <CRON_SECRET>`, compared in constant time. Without CRON_SECRET the endpoint is off (503).
"""
import hmac
import logging

from flask import Blueprint, current_app, jsonify, request

from web import tasks
from web.extensions import csrf, limiter

bp = Blueprint("internal", __name__, url_prefix="/internal")
csrf.exempt(bp)
log = logging.getLogger("web.internal")
MIN_SECRET_CHARS = 16  # a shorter CRON_SECRET counts as not set: it would be too easy to guess


def _authorized(secret: str) -> bool:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    return scheme.lower() == "bearer" and hmac.compare_digest(token.strip().encode(), secret.encode())


@bp.post("/sync-all")
@limiter.limit("1 per minute")  # counted before the token check: guessing is slow as well
def sync_all():
    secret = current_app.config["CRON_SECRET"]
    if len(secret) < MIN_SECRET_CHARS:
        log.warning("sync-all refused: CRON_SECRET is not configured")
        return jsonify(error="not configured"), 503
    if not _authorized(secret):
        log.warning("sync-all refused: missing or wrong token")
        return jsonify(error="unauthorized"), 401, {"WWW-Authenticate": "Bearer"}
    started = tasks.start_sync_all(current_app._get_current_object())
    status = "started" if started else "already running"
    log.info("sync-all accepted: %s", status)
    return jsonify(status=status), 202
