"""eClass Companion dashboard - local only.

    python app.py            # http://127.0.0.1:5050
"""
import argparse
import json
import os
import logging
import random
import re
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, g, jsonify, redirect, render_template, request, send_file, url_for

from eclass import chapters, config, db, i18n, rag, search, study, syncstatus, videos
from eclass.ai import AIError, AITimeout, DailyLimitReached, get_provider
from eclass.config import DATA_DIR, DB_PATH, ECLASS_URL, ROOT
from eclass.notify import is_submitted, parse_due

FILES_DIR = config.FILES_DIR.resolve()

# One stable accent per course (by id order), so a course is recognisable wherever it appears.
COURSE_COLORS = ["#f59e0b", "#14b8a6", "#f97360", "#3b82f6", "#84cc16", "#ec4899", "#8b5cf6", "#06b6d4"]
EN_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], 1)}

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("eclass.web")


def T(key, **kw):
    return i18n.t(g.lang, key, **kw)


LOCAL_HOSTS = {"127.0.0.1", "localhost"}


@app.before_request
def _language():
    g.lang = i18n.pick(request.args.get("lang") or request.cookies.get("lang"))


@app.before_request
def _guard():
    """Local-only app: reject foreign Host headers (DNS rebinding) and cross-site POSTs to /api/."""
    if (request.host or "").rsplit(":", 1)[0] not in LOCAL_HOSTS:
        abort(400)
    if request.method == "POST" and request.path.startswith("/api/"):
        source = request.headers.get("Origin") or request.headers.get("Referer") or ""
        if urlparse(source).netloc != request.host:
            log.warning("blocked cross-site POST to %s from %r", request.path, source[:100])
            abort(403)


def _error(code, exc=None):
    if request.path.startswith("/api/"):
        return jsonify(error=T(f"err.{code}.title")), code
    return render_template("error.html", code=code, title=T(f"err.{code}.title"), text=T(f"err.{code}.text"),
                           home=T("err.home")), code


for _code in (400, 403, 404, 405, 415):
    app.register_error_handler(_code, lambda exc, _c=_code: _error(_c))


@app.errorhandler(500)
def _server_error(exc):
    log.error("server error on %s", request.path, exc_info=getattr(exc, "original_exception", exc))
    return _error(500)


@app.after_request
def _remember_language(resp):
    if request.args.get("lang") in i18n.LANGS:
        resp.set_cookie("lang", g.lang, max_age=365 * 24 * 3600, samesite="Lax")
    return resp


def ai_failure(exc: Exception, what: str) -> tuple[str, int]:
    """Message key and HTTP status for a failed AI call; the full details go to the server log only."""
    if isinstance(exc, DailyLimitReached):
        log.warning("%s: daily AI limit reached: %s", what, exc)
        return "err.ai_quota", 429
    if isinstance(exc, AITimeout):
        log.warning("%s: AI too slow: %s", what, exc)
        return "err.ai_timeout", 504
    if isinstance(exc, AIError):
        log.error("%s: AI provider failed: %s", what, exc)
        return "err.ai", 502
    log.error("%s crashed", what, exc_info=exc)
    return "err.ai", 500


def conn():
    if "conn" not in g:
        g.conn = db.connect(DB_PATH)
    return g.conn


@app.teardown_appcontext
def _close(_exc):
    c = g.pop("conn", None)
    if c is not None:
        c.close()


# ---------------------------------------------------------------- helpers

def deadline(row, now):
    """Assignment row -> dict with a display state: done / overdue / soon / upcoming / nodate."""
    due = parse_due(row["due_date"])
    if is_submitted(row["submission_status"]):
        state = "done"
    elif due is None:
        state = "nodate"
    elif due < now:
        state = "overdue"
    elif due - now <= config.SOON_WINDOW:
        state = "soon"
    else:
        state = "upcoming"
    remaining = due - now if due and due > now else None
    return dict(row) | {
        "state": state,
        "due": due,
        "due_iso": due.isoformat() if due else None,
        "left": i18n.duration(g.lang, remaining) if remaining else None,
        "ring": min(1.0, remaining / config.DEADLINE_RING) if remaining else 0.0,
        "days_left": remaining.days if remaining else 0,
        "hours_left": int(remaining.total_seconds() // 3600) if remaining else 0,
    }


def grade_points(grade):
    """'22.00 / 25.00' -> (22.0, 25.0); None when the grade is not a score."""
    m = re.match(r"\s*([\d.]+)\s*/\s*([\d.]+)", grade or "")
    return (float(m.group(1)), float(m.group(2))) if m and float(m.group(2)) else None


def grade_percent(grade):
    points = grade_points(grade)
    return round(100 * points[0] / points[1]) if points else None


WEEK_RE = re.compile(r"^(\d+)\s*Week\s*\[(\d{1,2})\s+([A-Za-z]+)\s*-\s*(\d{1,2})\s+([A-Za-z]+)\]", re.I)


def week_info(name, today):
    """'3Week [19 September - 25 September]' -> localized title, date range and whether it is this week."""
    m = WEEK_RE.match(name or "")
    if not m:
        general = not name or name.lower().startswith("course")
        return {"title": T("week.general") if general else name, "range": None, "current": False, "past": False}
    number, d1, m1, d2, m2 = m.groups()
    try:
        start = date(today.year, EN_MONTHS[m1.lower()], int(d1))
        end = date(today.year, EN_MONTHS[m2.lower()], int(d2))
    except (KeyError, ValueError):
        return {"title": T("week.n", n=number), "range": None, "current": False, "past": False}
    if end < start:  # a week crossing New Year
        end = end.replace(year=end.year + 1)
    return {
        "title": T("week.n", n=number),
        "range": i18n.day_range(g.lang, start, end),
        "current": start <= today <= end,
        "past": end < today,
    }


ASSIGN_SQL = """
    SELECT s.*, a.name, a.url, a.course_id, c.name AS course,
           (SELECT COUNT(*) FROM files f WHERE f.activity_id = a.id) AS n_files
    FROM assignments s JOIN activities a ON a.id = s.activity_id
    JOIN courses c ON c.id = a.course_id"""

STATE_ORDER = {"overdue": 0, "soon": 1, "upcoming": 2, "nodate": 3, "done": 4}


def all_assignments(course_id=None):
    now = datetime.now().astimezone()
    sql, params = ASSIGN_SQL, ()
    if course_id is not None:
        sql, params = sql + " WHERE a.course_id = ?", (course_id,)
    items = [deadline(r, now) for r in conn().execute(sql, params)]
    far = datetime.max.replace(tzinfo=now.tzinfo)
    items.sort(key=lambda d: (STATE_ORDER[d["state"]], d["due"] or far))
    return items


def courses():
    return conn().execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM files f JOIN activities a ON a.id = f.activity_id
                   WHERE a.course_id = c.id AND a.type != 'assign') AS n_files,
                  (SELECT COUNT(*) FROM study s JOIN files f ON f.id = s.file_id AND f.sha256 = s.sha256
                   JOIN activities a ON a.id = f.activity_id WHERE a.course_id = c.id) AS n_study,
                  (SELECT COUNT(*) FROM activities a WHERE a.course_id = c.id AND a.type = 'assign') AS n_assign
           FROM courses c ORDER BY c.name""").fetchall()


def _colors():
    if "colors" not in g:
        ids = [r["id"] for r in conn().execute("SELECT id FROM courses ORDER BY id")]
        g.colors = {cid: COURSE_COLORS[i % len(COURSE_COLORS)] for i, cid in enumerate(ids)}
    return g.colors


@app.context_processor
def _globals():
    g.lang = g.get("lang", i18n.DEFAULT)
    page = {"last_sync": "—", "sync_fresh": False, "sync_status": {"state": "none"},
            "course_color": lambda cid: COURSE_COLORS[0]}
    try:  # an error page must still render when the database is the problem
        now = datetime.now().astimezone()
        last = conn().execute("SELECT MAX(last_seen) AS t FROM courses").fetchone()["t"]
        synced = datetime.fromisoformat(last).astimezone() if last else None
        colors = _colors()
        page = {"last_sync": i18n.ago(g.lang, now - synced) if synced else T("sync.never"),
                "sync_fresh": bool(synced and now - synced < config.SYNC_FRESH),
                "sync_status": sync_status(),
                "course_color": lambda cid: colors.get(cid, COURSE_COLORS[0])}
    except Exception:
        log.exception("page context unavailable")
    return page | {
        "eclass_url": ECLASS_URL,
        "t": T,
        "pl": lambda n, word: i18n.plural(g.lang, n, word),
        "lang": g.lang,
        "langs": i18n.LANGS,
        "lang_url": lang_url,
        "js_t": i18n.js_strings(g.lang),
        "is_book": chapters.is_book,
        "status_label": lambda s: T(f"status.{s.lower()}") if s and f"status.{s.lower()}" in i18n.S else (s or ""),
    }


def sync_status():
    """Latest sync state for the page, with a localized error message."""
    status = syncstatus.read(DATA_DIR)
    if status.get("state") == "running" and not syncstatus.busy(DATA_DIR):
        started = datetime.fromisoformat(status.get("started", "1970-01-01T00:00:00+00:00"))
        if datetime.now(started.tzinfo) - started > config.SYNC_START_GRACE:  # died without writing a result
            status = status | {"state": "error", "code": "stopped"}
    if status.get("state") == "error":
        status["message"] = sync_error_text(status.get("code"))
    return status


def sync_error_text(code: str | None) -> str:
    key = f"sync.err.{code}"
    return T(key if key in i18n.S else "sync.err.other")


def sync_history() -> list[dict]:
    """The latest sync attempts for the home page, newest first, each with a localized outcome."""
    rows, running = db.sync_runs(conn(), config.SYNC_HISTORY), syncstatus.busy(DATA_DIR)
    out = []
    for i, r in enumerate(rows):
        state, new, errors = r["state"], r["new_items"], r["errors"]
        if state == "running" and not (running and i == 0):
            state = "stopped"  # the process died without recording a result
        if state == "done" and errors:
            state, text = "partial", T("sync.hist.partial", n=new, e=errors)
        elif state == "done":
            text = T("sync.hist.new", n=new) if new else T("sync.hist.nothing")
        elif state == "error":
            text = sync_error_text(r["code"])
        elif state == "running":
            text = T("sync.hist.running")
        else:
            text = T("sync.err.stopped")
        by = f"sync.by.{r['started_by']}"
        out.append({"state": state, "text": text, "detail": r["detail"], "by": T(by) if by in i18n.S else r["started_by"],
                    "when": i18n.short_date(g.lang, datetime.fromisoformat(r["started_at"]).astimezone())})
    return out


def lang_url(code):
    args = {**request.args.to_dict(), "lang": code}
    if request.endpoint and request.endpoint != "static":
        return url_for(request.endpoint, **(request.view_args or {}), **args)
    return url_for("index", lang=code)


@app.template_filter("size")
def _size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


@app.template_filter("dt")
def _dt(value):
    return i18n.short_date(g.lang, value) if value else "—"


@app.template_filter("ext")
def _ext(name):
    return Path(name).suffix.lstrip(".").upper()[:4] or "FILE"


# ---------------------------------------------------------------- pages

@app.route("/")
def index():
    now = datetime.now().astimezone()
    items = all_assignments()
    pending = [d for d in items if d["state"] != "done"]
    upcoming = [d for d in pending if d["due"] and d["due"] > now]
    graded = [d | {"pct": grade_percent(d["grade"])} for d in items if d["grade"]]
    pcts = [d["pct"] for d in graded if d["pct"] is not None]
    c = conn()
    stats = {
        "pending": len(pending),
        "avg": round(sum(pcts) / len(pcts)) if pcts else None,
        "materials": c.execute(
            "SELECT COUNT(*) FROM files f JOIN activities a ON a.id = f.activity_id WHERE a.type != 'assign'"
        ).fetchone()[0],
        "packs": c.execute(
            "SELECT COUNT(*) FROM study s JOIN files f ON f.id = s.file_id AND f.sha256 = s.sha256").fetchone()[0],
    }
    materials = c.execute(
        """SELECT f.id, f.filename, f.downloaded_at, a.name AS activity, c.id AS course_id,
                  c.name AS course, (s.file_id IS NOT NULL) AS has_study,
                  (SELECT n_chars FROM extractions e WHERE e.file_id = f.id) AS n_chars,
                  EXISTS (SELECT 1 FROM progress p WHERE p.file_id = f.id) AS studied
           FROM files f JOIN activities a ON a.id = f.activity_id JOIN courses c ON c.id = a.course_id
           LEFT JOIN study s ON s.file_id = f.id AND s.sha256 = f.sha256
           WHERE a.type != 'assign' AND f.path NOT LIKE 'youtube:%'
           ORDER BY f.downloaded_at DESC, f.id DESC LIMIT 7""").fetchall()
    today_plan = plan_for_today(c, pending, now)
    hour = now.hour
    part = ("morning" if 5 <= hour < 11 else "day" if 11 <= hour < 17 else "evening" if 17 <= hour < 22
            else "night")
    return render_template(
        "index.html", pending=pending, next_due=upcoming[0] if upcoming else None, graded=graded,
        materials=materials, course_list=courses(), stats=stats, greeting=T(f"greet.{part}"), plan=today_plan,
        today=i18n.long_date(g.lang, now), history=sync_history())


def plan_for_today(c, pending, now):
    """Deadlines this week, the newest unstudied material and one concrete suggestion."""
    week = now + timedelta(days=7)
    due = [d for d in pending if d["state"] in ("overdue", "soon") or (d["due"] and d["due"] <= week)][:3]
    unread = c.execute(
        """SELECT f.id, a.name AS activity, co.id AS course_id, co.name AS course
           FROM study s JOIN files f ON f.id = s.file_id AND f.sha256 = s.sha256
           JOIN activities a ON a.id = f.activity_id JOIN courses co ON co.id = a.course_id
           WHERE a.type != 'assign' AND NOT EXISTS (SELECT 1 FROM progress p WHERE p.file_id = f.id)
           ORDER BY f.downloaded_at DESC, f.id DESC LIMIT 1""").fetchone()
    first = {state: next((d for d in pending if d["state"] == state), None) for state in ("overdue", "soon", "upcoming")}
    assign_url = lambda d: f"{ECLASS_URL}/mod/assign/view.php?id={d['activity_id']}"
    if first["overdue"]:
        tip = (T("tip.overdue", name=first["overdue"]["name"]), assign_url(first["overdue"]))
    elif first["soon"]:
        tip = (T("tip.soon", name=first["soon"]["name"], left=first["soon"]["left"]), assign_url(first["soon"]))
    elif unread:
        tip = (T("tip.study", name=unread["activity"]), url_for("study_page", file_id=unread["id"]))
    elif first["upcoming"]:
        tip = (T("tip.upcoming", name=first["upcoming"]["name"], left=first["upcoming"]["left"]),
               assign_url(first["upcoming"]))
    else:
        review = c.execute(
            """SELECT f.id, a.name FROM study s JOIN files f ON f.id = s.file_id JOIN activities a ON a.id = f.activity_id
               ORDER BY random() LIMIT 1""").fetchone()
        tip = (T("tip.review", name=review["name"]), url_for("study_page", file_id=review["id"]) + "#quiz") if review else None
    return {"due": due, "unread": unread, "tip": tip}


@app.route("/api/studied/<int:file_id>", methods=["POST"])
def api_studied(file_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(415)
    c = conn()
    if c.execute("SELECT 1 FROM files WHERE id = ?", (file_id,)).fetchone() is None:
        abort(404)
    if data.get("studied"):
        c.execute("INSERT OR IGNORE INTO progress (file_id, studied_at) VALUES (?, ?)", (file_id, db.now()))
    else:
        c.execute("DELETE FROM progress WHERE file_id = ?", (file_id,))
    c.commit()
    return jsonify(studied=bool(data.get("studied")))


@app.route("/course/<int:course_id>")
def course(course_id):
    info = next((c for c in courses() if c["id"] == course_id), None)
    if info is None:
        abort(404)
    c = conn()
    sections = c.execute(
        "SELECT * FROM sections WHERE course_id = ? ORDER BY number", (course_id,)).fetchall()
    acts = c.execute(
        "SELECT * FROM activities WHERE course_id = ? ORDER BY section, id", (course_id,)).fetchall()
    files = {}
    for f in c.execute(
            """SELECT f.id, f.activity_id, f.filename, f.size, (s.file_id IS NOT NULL) AS has_study,
                      (SELECT n_chars FROM extractions e WHERE e.file_id = f.id) AS n_chars
               FROM files f JOIN activities a ON a.id = f.activity_id
               LEFT JOIN study s ON s.file_id = f.id AND s.sha256 = f.sha256
               WHERE a.course_id = ? ORDER BY f.filename""", (course_id,)):
        files.setdefault(f["activity_id"], []).append(f)
    assigns = {d["activity_id"]: d for d in all_assignments(course_id)}
    by_section = {}
    for a in acts:
        by_section.setdefault(a["section"], []).append(a)
    today = date.today()
    weeks = [(s, week_info(s["name"], today), by_section[s["number"]])
             for s in sections if by_section.get(s["number"])]
    return render_template("course.html", course=info, weeks=weeks, files=files, assigns=assigns,
                           video=videos.for_course(c, course_id))


@app.route("/study/<int:file_id>")
def study_page(file_id):
    row = conn().execute(
        """SELECT s.*, f.filename, a.name AS activity, c.id AS course_id, c.name AS course
           FROM study s JOIN files f ON f.id = s.file_id JOIN activities a ON a.id = f.activity_id
           JOIN courses c ON c.id = a.course_id WHERE s.file_id = ?""", (file_id,)).fetchone()
    if row is None:
        abort(404)
    pack, translating = row, False
    if row["language"] != g.lang:  # show a cached translation, or the original while one is made
        cached = conn().execute(
            "SELECT * FROM study_i18n WHERE file_id = ? AND language = ? AND sha256 = ?",
            (file_id, g.lang, row["sha256"])).fetchone()
        pack, translating = (cached, False) if cached else (row, True)
    studied = conn().execute("SELECT 1 FROM progress WHERE file_id = ?", (file_id,)).fetchone() is not None
    return render_template("study.html", s=row, summary=pack["summary"], concepts=json.loads(pack["concepts"]),
                           flashcards=json.loads(pack["flashcards"]), quiz=json.loads(pack["quiz"]),
                           translating=translating, studied=studied)


# ---------------------------------------------------------------- textbooks: chapters on demand

_jobs, _jobs_lock = {}, threading.Lock()  # (file_id, idx) -> {"state": running|done|error, "step": "3/8"}


def _chapter_worker(file_id, idx):
    key, own = (file_id, idx), db.connect(DB_PATH)

    def progress(msg):
        m = re.search(r"notes (\d+)/(\d+)", msg)
        if m:
            _jobs[key]["step"] = f"{m.group(1)}/{m.group(2)}"
    try:
        chapters.generate(own, get_provider(), file_id, idx, log=progress)
        _jobs[key] = {"state": "done"}
    except Exception as exc:  # the page polls the job and shows the message
        _jobs[key] = {"state": "error", "message_key": ai_failure(exc, f"chapter {file_id}/{idx}")[0]}
    finally:
        own.close()


def _book_file(file_id):
    row = conn().execute(
        """SELECT f.*, e.n_chars, a.name AS activity, c.id AS course_id, c.name AS course
           FROM files f JOIN extractions e ON e.file_id = f.id AND e.error IS NULL
           JOIN activities a ON a.id = f.activity_id JOIN courses c ON c.id = a.course_id WHERE f.id = ?""",
        (file_id,)).fetchone()
    if row is None or not chapters.is_book(row["n_chars"]):
        abort(404)
    return row


@app.route("/book/<int:file_id>")
def book(file_id):
    f = _book_file(file_id)
    rows = chapters.ensure(conn(), f)
    running = {idx: job for (fid, idx), job in _jobs.items() if fid == file_id and job.get("state") == "running"}
    return render_template("book.html", f=f, chapters=rows, running=running)


@app.route("/api/chapter/<int:file_id>/<int:idx>", methods=["GET", "POST"])
def api_chapter(file_id, idx):
    key = (file_id, idx)
    row = conn().execute("SELECT summary FROM chapters WHERE file_id = ? AND idx = ?", key).fetchone()
    if row is None:
        abort(404)
    if row["summary"]:
        return jsonify(state="done")
    if request.method == "POST":
        if not request.is_json:
            abort(415)
        with _jobs_lock:
            if _jobs.get(key, {}).get("state") != "running":
                if any(j.get("state") == "running" for j in _jobs.values()):
                    return jsonify(state="busy", message=T("book.busy")), 409
                _jobs[key] = {"state": "running", "step": ""}
                threading.Thread(target=_chapter_worker, args=key, daemon=True).start()
    job = dict(_jobs.get(key, {"state": "idle"}))
    if job["state"] == "error":
        job["message"] = T(job.pop("message_key"))
    return jsonify(job)


@app.route("/study/<int:file_id>/ch/<int:idx>")
def chapter_page(file_id, idx):
    f = _book_file(file_id)
    ch = conn().execute("SELECT * FROM chapters WHERE file_id = ? AND idx = ?", (file_id, idx)).fetchone()
    if ch is None or not ch["summary"]:
        abort(404)
    title = ch["title"] or T("book.pages", a=ch["start_page"], b=ch["end_page"])
    s = {"file_id": file_id, "activity": title, "course": f["course"], "course_id": f["course_id"],
         "filename": f["filename"], "model": ch["model"], "language": ch["language"]}
    return render_template("study.html", s=s, summary=ch["summary"], concepts=json.loads(ch["concepts"]),
                           flashcards=json.loads(ch["flashcards"]), quiz=json.loads(ch["quiz"]), translating=False,
                           back_url=url_for("book", file_id=file_id), back_label=f["activity"])


@app.route("/api/translate/<int:file_id>", methods=["POST"])
def api_translate(file_id):
    if not request.is_json:
        abort(415)
    try:
        study.translate_pack(conn(), get_provider(), file_id, g.lang)
    except LookupError:
        abort(404)
    except Exception as exc:
        key, status = ai_failure(exc, f"translate {file_id} -> {g.lang}")
        return jsonify(error=T(key)), status
    return jsonify(ok=True)


@app.route("/grades")
def grades():
    items = [d | {"pct": grade_percent(d["grade"])} for d in all_assignments()]
    items.sort(key=lambda d: (d["course"], d["due_date"] or ""))
    pcts = [d["pct"] for d in items if d["pct"] is not None]
    groups = {}
    for d in items:
        g = groups.setdefault(d["course_id"], {"course_id": d["course_id"], "course": d["course"],
                                               "graded": [], "ungraded": [], "earned": 0.0, "possible": 0.0})
        points = grade_points(d["grade"])
        (g["graded"] if d["grade"] else g["ungraded"]).append(d)
        if points:
            g["earned"] += points[0]
            g["possible"] += points[1]
    for g in groups.values():
        course_pcts = [d["pct"] for d in g["graded"] if d["pct"] is not None]
        g["pct"] = round(100 * g["earned"] / g["possible"]) if g["possible"] else None
        g["avg"] = round(sum(course_pcts) / len(course_pcts)) if course_pcts else None
    by_course = sorted(groups.values(), key=lambda g: (g["pct"] is None, g["course"]))
    summary = {
        "avg": round(sum(pcts) / len(pcts)) if pcts else None,
        "graded": len(pcts),
        "done": sum(d["state"] == "done" for d in items),
        "total": len(items),
    }
    return render_template("grades.html", items=items, summary=summary, by_course=by_course)


def question_suggestions():
    """Key concepts from the study packs, per course id ('' = all courses), as question starters."""
    rows = conn().execute(
        """SELECT a.course_id, s.concepts FROM study s JOIN files f ON f.id = s.file_id
           JOIN activities a ON a.id = f.activity_id""")
    terms = {}
    for r in rows:
        for concept in json.loads(r["concepts"]):
            term = re.sub(r"\s*\([^)]*\)", "", concept["term"]).strip()
            if 2 < len(term) <= 40:
                terms.setdefault(r["course_id"], []).append(term)
    rng = random.Random()
    out = {}
    for cid, ts in terms.items():
        unique = list(dict.fromkeys(ts))
        out[str(cid)] = rng.sample(unique, min(4, len(unique)))
    everything = list(dict.fromkeys(t for ts in terms.values() for t in ts))
    out[""] = rng.sample(everything, min(4, len(everything)))
    return out


@app.route("/ask")
def ask_page():
    return render_template("ask.html", course_list=courses(), suggestions=question_suggestions(),
                           selected=request.args.get("course", type=int), timeout_ms=(config.AI_CHAT_BUDGET + 15) * 1000)


@app.route("/api/ask", methods=["POST"])
def api_ask():
    # JSON only: a cross-site form cannot send application/json without a CORS preflight
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(415)
    question = str(data.get("question", "")).strip()
    if not question or len(question) > 1000:
        return jsonify(error=T("err.question")), 400
    course_id = data.get("course_id") or None
    history = [{"q": str(h.get("q", ""))[:2000], "a": str(h.get("a", ""))[:2000]}
               for h in (data.get("history") or []) if isinstance(h, dict)][-rag.HISTORY_TURNS:]

    def ask(provider):
        return rag.answer(conn(), provider, question, course_id=int(course_id) if course_id else None,
                          language=i18n.AI_LANGUAGE[g.lang], history=history, not_found=T("ask.not_found"))
    try:
        # every model gets AI_CHAT_TIMEOUT seconds, the whole answer AI_CHAT_BUDGET: slow models are skipped
        provider = get_provider(timeout=config.AI_CHAT_TIMEOUT, deadline=time.monotonic() + config.AI_CHAT_BUDGET)
        try:
            result = ask(provider)
        except (DailyLimitReached, AITimeout):
            raise
        except AIError as exc:  # transient provider hiccup: one retry after a short pause
            log.warning("ask failed, retrying once: %s", exc)
            time.sleep(2)
            result = ask(provider)
    except Exception as exc:  # never show a traceback to the page; details go to the log only
        key, status = ai_failure(exc, "ask")
        return jsonify(error=T(key)), status
    return jsonify(result)


@app.route("/api/search")
def api_search():
    c, colors = conn(), _colors()
    names = {r["id"]: r["name"] for r in c.execute("SELECT id, name FROM courses")}
    results = []
    for r in search.query(c, request.args.get("q", "")[:200]):
        kind, ref, external = r["kind"], r["ref"], False
        if kind == "course":
            url = url_for("course", course_id=ref)
        elif kind == "study":
            url = url_for("study_page", file_id=ref)
        elif kind == "chapter":
            file_id, idx = ref.split("/")
            url = url_for("chapter_page", file_id=int(file_id), idx=int(idx))
        elif kind == "file":
            url, external = url_for("file_view", file_id=ref), True
        elif kind == "assign":
            url, external = f"{ECLASS_URL}/mod/assign/view.php?id={ref}", True
        else:  # other course activities (videos, boards): the course page lists them
            url = url_for("course", course_id=r["course_id"])
        results.append({"kind": kind, "kind_label": T(f"kind.{kind}"), "url": url, "external": external,
                        "title_html": r["title_html"], "snippet_html": r["snippet_html"],
                        "course": names.get(r["course_id"], ""), "color": colors.get(r["course_id"], COURSE_COLORS[0])})
    return jsonify(results=results)


@app.route("/api/sync", methods=["POST"])
def api_sync():
    if not request.is_json:
        abort(415)
    if not syncstatus.busy(DATA_DIR):
        syncstatus.write(DATA_DIR, {"state": "running", "started": db.now(), "by": "dashboard"})
        (DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
        with open(DATA_DIR / "logs" / "sync.log", "a") as out:
            subprocess.Popen([sys.executable, "-u", str(ROOT / "sync.py"), "--all", "--trigger", "dashboard"], cwd=ROOT,
                             stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        log.info("sync started from the dashboard")
    return jsonify(sync_status()), 202


@app.route("/api/sync/status")
def api_sync_status():
    return jsonify(sync_status())


@app.route("/file/<int:file_id>")
def file_view(file_id):
    row = conn().execute("SELECT path, filename, source_url FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        abort(404)
    if row["path"].startswith("youtube:"):  # a lecture transcript: open the video itself
        return redirect(row["source_url"] or f"https://youtu.be/{row['path'][8:]}")
    path = Path(row["path"]).resolve()
    if not path.is_relative_to(FILES_DIR) or not path.is_file():
        abort(404)
    return send_file(path, download_name=row["filename"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=5050)
    args = ap.parse_args()
    # local only (.env is loaded by eclass.config); the debugger stays off unless FLASK_DEBUG=1 is set
    app.run(host="127.0.0.1", port=args.port, debug=os.getenv("FLASK_DEBUG") == "1")


if __name__ == "__main__":
    main()
