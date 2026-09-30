"""The student's pages (home, a course, grades), files streamed from eClass, and the sync status / refresh."""
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlparse

from flask import (Blueprint, Response, abort, current_app, flash, g, jsonify, redirect, render_template, request,
                   stream_with_context, url_for)
from flask_login import current_user, login_required
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from eclass import i18n as base_i18n
from eclass.auth import EClassError, LoginError, SessionExpired
from eclass.config import ECLASS_URL
from web import autosync, dashboard, eclass_login, packs, sync, tasks
from web import db as database
from web.extensions import limiter
from web.models import Activity, Course, Progress
from web.views import T

bp = Blueprint("dashboard", __name__)
INLINE_TYPES = ("application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp")
FRESH = timedelta(hours=6)  # the sync dot is green when the last sync is newer than this


def sync_status(db, user_id: int) -> dict:
    """The latest sync of this student: `message` for the banner and tooltip, `short` for the pill in the top bar."""
    if sync.is_running(db, user_id):
        return {"state": "running", "message": T("web.sync.running"), "short": T("js.sync_running")}
    if tasks.waiting(user_id):  # queued behind other students' syncs in this process
        return {"state": "running", "message": T("web.sync.queued"), "short": T("js.sync_running")}
    sync.reap(db, user_id)  # a "running" run without a live process (the server restarted) is closed
    run = sync.latest_run(db, user_id)
    if run is None:
        return {"state": "none", "message": T("sync.never"), "short": T("sync.never")}
    finished = run.finished_at or run.started_at
    when = base_i18n.ago(g.lang, datetime.now(timezone.utc) - finished)
    if run.status == "done":
        return {"state": "done", "message": T("web.sync.last", when=when), "short": when,
                "fresh": datetime.now(timezone.utc) - finished < FRESH}
    if run.error_code == "session":
        return {"state": "expired", "message": T("web.sync.expired"), "short": T("web.sync.reconnect")}
    if run.error_code == "login":  # eClass refused the stored password: background sync stopped
        return {"state": "expired", "message": T("web.autosync.invalid"), "short": T("web.sync.reconnect")}
    key = f"sync.err.{run.error_code}"
    reason = T(key) if run.error_code not in ("other", "page", None) and key in base_i18n.S else T("web.sync.err.other")
    return {"state": "error", "message": T("web.sync.failed", reason=reason), "short": T("js.sync_failed")}


@bp.get("/")
@login_required
def home():
    db, uid = database.session(), current_user.id
    items = dashboard.assignments(db, uid, g.lang)
    pending = [a for a in items if a["state"] != "done"]
    course_list = dashboard.courses(db, uid)
    now = datetime.now(dashboard.TZ)
    part = ("morning" if 5 <= now.hour < 11 else "day" if 11 <= now.hour < 17 else "evening" if now.hour < 22
            else "night")
    materials = dashboard.recent_materials(db, uid, limit=7)
    return render_template("home.html", status=sync_status(db, uid), pending=pending[:8],
                           next_due=next((a for a in pending if a["left"]), None),
                           graded=[a for a in items if a["grade"]][:6], courses=course_list, materials=materials,
                           ready=packs.with_packs(db, [m["id"] for m in materials]),
                           stats=dashboard.home_stats(items, course_list), greeting=T(f"greet.{part}"),
                           today=base_i18n.long_date(g.lang, now), autosync=autosync.state(db, uid))


@bp.get("/course/<int:course_id>")
@login_required
def course(course_id: int):
    db = database.session()
    page = dashboard.course_page(db, current_user.id, course_id, g.lang)
    if page is None:  # not enrolled (or no such course): the same answer, nothing is revealed
        abort(404)
    ready = packs.with_packs(db, [f.id for files in page["files"].values() for f in files])
    return render_template("course.html", ready=ready, **page)


@bp.get("/study/<int:material_id>")
@login_required
def study(material_id: int):
    """The study pack of one material: summary and key concepts, flashcards, quiz."""
    db = database.session()
    material = dashboard.material_for(db, current_user.id, material_id)
    pack = packs.pack_for(db, material_id) if material else None
    if pack is None:
        abort(404)
    activity = db.get(Activity, material.activity_id)
    return render_template("study.html", material=material, activity=activity, pack=pack,
                           course=db.get(Course, activity.course_id),
                           studied=db.get(Progress, (current_user.id, material_id)) is not None)


@bp.post("/api/studied/<int:material_id>")
@login_required
def studied(material_id: int):
    """Mark a material as studied (or not) for this student."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error=T("err.415.title")), 415
    db = database.session()
    if dashboard.material_for(db, current_user.id, material_id) is None:
        abort(404)
    if data.get("studied"):
        db.execute(insert(Progress).values(user_id=current_user.id, material_id=material_id)
                   .on_conflict_do_nothing())
    else:
        db.execute(delete(Progress).where(Progress.user_id == current_user.id, Progress.material_id == material_id))
    db.commit()
    return jsonify(ok=True)


@bp.get("/grades")
@login_required
def grades():
    items = dashboard.assignments(database.session(), current_user.id, g.lang)
    return render_template("grades.html", summary=dashboard.grade_summary(items),
                           groups=dashboard.grades(database.session(), current_user.id, g.lang, items))


def _eclass_client(db, user_id: int):
    """The student's eClass session: the saved one, else a new one from their stored password (if they opted
    into background sync); None when they have to enter their password."""
    cookies = eclass_login.load_session(db, user_id)
    db.commit()
    if cookies is not None:
        return eclass_login.EClassClient(cookies=cookies)
    if autosync.state(db, user_id) != "on":
        return None
    try:
        return sync.renew_session(db, user_id)
    except LoginError:  # eClass refused the stored password: it is forgotten, the page asks for the new one
        return None


@bp.get("/file/<int:material_id>")
@login_required
def file(material_id: int):
    """Stream a file from eClass with the student's own session; nothing is stored on this server."""
    db = database.session()
    material = dashboard.material_for(db, current_user.id, material_id)
    if material is None or urlparse(material.eclass_url).netloc != urlparse(ECLASS_URL).netloc:
        abort(404)
    try:
        client = _eclass_client(db, current_user.id)
    except EClassError:
        abort(503)
    if client is None:
        flash(T("web.sync.expired"), "error")
        return redirect(url_for("auth.reconnect"))
    try:
        resp = client.get(material.eclass_url, stream=True)
    except SessionExpired:
        eclass_login.drop_session(db, current_user.id)
        db.commit()
        flash(T("web.sync.expired"), "error")
        return redirect(url_for("auth.reconnect"))
    except EClassError:
        abort(503)
    mimetype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    inline = mimetype in INLINE_TYPES  # anything else downloads: an HTML file from eClass never runs on our site
    headers = {"Content-Disposition": f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{quote(material.filename)}",
               "Cache-Control": "private, no-store"}

    def body():
        try:
            yield from resp.iter_content(64 * 1024)
        finally:
            resp.close()
    return Response(stream_with_context(body()), headers=headers,
                    mimetype=mimetype if inline else "application/octet-stream")


@bp.post("/sync")
@login_required
@limiter.limit("3 per minute")
def refresh():
    db = database.session()
    alive = eclass_login.load_session(db, current_user.id) is not None or autosync.state(db, current_user.id) == "on"
    db.commit()
    if not alive:  # the background sync logs in with the stored password when the student opted in
        return redirect(url_for("auth.reconnect"))
    tasks.start_sync(current_app._get_current_object(), current_user.id, "button")
    return redirect(url_for("dashboard.home"))


@bp.get("/sync/status")
@login_required
def status():
    return jsonify(sync_status(database.session(), current_user.id))
