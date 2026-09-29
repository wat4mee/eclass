"""Shahzod AI: questions about the student's own course materials (Gemini + Postgres full-text search)."""
import logging
import time
from datetime import date

from flask import Blueprint, current_app, g, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from eclass import config as eclass_config
from eclass import i18n as base_i18n
from eclass import rag
from eclass.ai import AIError, AITimeout, DailyLimitReached, get_provider
from web import dashboard, search
from web import db as database
from web.models import AIUsage
from web.views import T

bp = Blueprint("ask", __name__)
log = logging.getLogger("web.ask")


def provider():
    """The configured AI chain for one chat answer; local-only providers (Ollama) are never used when hosted."""
    chain = get_provider(timeout=eclass_config.AI_CHAT_TIMEOUT,
                         deadline=time.monotonic() + eclass_config.AI_CHAT_BUDGET)
    if current_app.config["HOSTED"]:
        chain.providers = [p for p in chain.providers if p.name != "ollama"]
        if not chain.providers:
            raise AIError("no hosted AI provider configured")
    return chain


def _failure(exc: Exception) -> tuple[str, int]:
    if isinstance(exc, DailyLimitReached):
        return "err.ai_quota", 429
    if isinstance(exc, AITimeout):
        return "err.ai_timeout", 504
    if isinstance(exc, AIError):
        log.warning("chat: AI provider failed: %s", exc)
        return "err.ai", 502
    log.exception("chat crashed")
    return "err.ai", 500


def _used_today(db, user_id: int) -> int:
    return db.scalar(select(AIUsage.count).where(AIUsage.user_id == user_id, AIUsage.day == date.today())) or 0


def _count(db, user_id: int) -> None:
    db.execute(insert(AIUsage).values(user_id=user_id, day=date.today(), count=1)
               .on_conflict_do_update(index_elements=["user_id", "day"], set_={"count": AIUsage.count + 1}))


@bp.get("/ask")
@login_required
def ask_page():
    courses = dashboard.courses(database.session(), current_user.id)
    selected = request.args.get("course", type=int)
    return render_template("ask.html", courses=courses,
                           selected=selected if selected in {c["id"] for c in courses} else None,
                           js_t=base_i18n.js_strings(g.lang))


@bp.post("/api/ask")
@login_required
def api_ask():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error=T("err.415.title")), 415
    question = str(data.get("question", "")).strip()
    if not question or len(question) > 1000:
        return jsonify(error=T("err.question")), 400
    db, uid = database.session(), current_user.id
    course_name = None
    if data.get("course_id"):
        crs = dashboard.course(db, uid, int(data["course_id"])) if str(data["course_id"]).isdigit() else None
        if crs is None:
            return jsonify(error=T("err.404.title")), 404
        course_name = crs.name
    course_id = int(data["course_id"]) if course_name else None
    limit = current_app.config["AI_DAILY_LIMIT"]
    if _used_today(db, uid) >= limit:
        return jsonify(error=T("web.ask.limit", n=limit)), 429
    history = [{"q": str(h.get("q", ""))[:2000], "a": str(h.get("a", ""))[:2000]}
               for h in (data.get("history") or []) if isinstance(h, dict)][-rag.HISTORY_TURNS:]
    try:
        result = rag.answer(None, provider(), question, course_id=course_id, course_name=course_name,
                            language=base_i18n.AI_LANGUAGE[g.lang], history=history,
                            not_found=T("ask.not_found"),
                            search_fn=lambda query: search.passages(db, uid, query, course_id))
    except Exception as exc:  # the student sees a short message; details go to the server log only
        key, status = _failure(exc)
        return jsonify(error=T(key)), status
    _count(db, uid)
    db.commit()
    return jsonify(result)
