"""eClass Companion dashboard - local only.

    python app.py            # http://127.0.0.1:5050
"""
import argparse
import json
import logging
import random
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, abort, g, jsonify, render_template, request, send_file, url_for

from eclass import db, i18n, rag, study
from eclass.ai import AIError, DailyLimitReached, get_provider
from eclass.notify import is_submitted, parse_due

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "eclass.db"
FILES_DIR = (ROOT / "data" / "files").resolve()
ECLASS_URL = "https://eclass.inha.ac.kr"

# One stable accent per course (by id order), so a course is recognisable wherever it appears.
COURSE_COLORS = ["#f59e0b", "#14b8a6", "#f97360", "#3b82f6", "#84cc16", "#ec4899", "#8b5cf6", "#06b6d4"]
EN_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], 1)}
DEADLINE_WINDOW = timedelta(days=7)  # the countdown ring is full a week before a deadline

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("eclass.web")


def T(key, **kw):
    return i18n.t(g.lang, key, **kw)


@app.before_request
def _language():
    g.lang = i18n.pick(request.args.get("lang") or request.cookies.get("lang"))


@app.after_request
def _remember_language(resp):
    if request.args.get("lang") in i18n.LANGS:
        resp.set_cookie("lang", g.lang, max_age=365 * 24 * 3600, samesite="Lax")
    return resp


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
    elif due - now <= timedelta(hours=48):
        state = "soon"
    else:
        state = "upcoming"
    remaining = due - now if due and due > now else None
    return dict(row) | {
        "state": state,
        "due": due,
        "due_iso": due.isoformat() if due else None,
        "left": i18n.duration(g.lang, remaining) if remaining else None,
        "ring": min(1.0, remaining / DEADLINE_WINDOW) if remaining else 0.0,
        "days_left": remaining.days if remaining else 0,
        "hours_left": int(remaining.total_seconds() // 3600) if remaining else 0,
    }


def grade_percent(grade):
    m = re.match(r"\s*([\d.]+)\s*/\s*([\d.]+)", grade or "")
    return round(100 * float(m.group(1)) / float(m.group(2))) if m and float(m.group(2)) else None


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
    now = datetime.now().astimezone()
    last = conn().execute("SELECT MAX(last_seen) AS t FROM courses").fetchone()["t"]
    synced = datetime.fromisoformat(last).astimezone() if last else None
    colors = _colors()
    return {
        "eclass_url": ECLASS_URL,
        "last_sync": i18n.ago(g.lang, now - synced) if synced else T("sync.never"),
        "sync_fresh": bool(synced and now - synced < timedelta(hours=4)),
        "course_color": lambda cid: colors.get(cid, COURSE_COLORS[0]),
        "t": T,
        "pl": lambda n, word: i18n.plural(g.lang, n, word),
        "lang": g.lang,
        "langs": i18n.LANGS,
        "lang_url": lang_url,
        "js_t": i18n.js_strings(g.lang),
        "status_label": lambda s: T(f"status.{s.lower()}") if s and f"status.{s.lower()}" in i18n.S else (s or ""),
    }


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
                  c.name AS course, (s.file_id IS NOT NULL) AS has_study
           FROM files f JOIN activities a ON a.id = f.activity_id JOIN courses c ON c.id = a.course_id
           LEFT JOIN study s ON s.file_id = f.id AND s.sha256 = f.sha256
           WHERE a.type != 'assign' ORDER BY f.downloaded_at DESC, f.id DESC LIMIT 7""").fetchall()
    hour = now.hour
    part = ("morning" if 5 <= hour < 11 else "day" if 11 <= hour < 17 else "evening" if 17 <= hour < 22
            else "night")
    return render_template(
        "index.html", pending=pending, next_due=upcoming[0] if upcoming else None, graded=graded,
        materials=materials, course_list=courses(), stats=stats, greeting=T(f"greet.{part}"),
        today=i18n.long_date(g.lang, now))


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
            """SELECT f.id, f.activity_id, f.filename, f.size, (s.file_id IS NOT NULL) AS has_study
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
    return render_template("course.html", course=info, weeks=weeks, files=files, assigns=assigns)


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
    return render_template("study.html", s=row, summary=pack["summary"], concepts=json.loads(pack["concepts"]),
                           flashcards=json.loads(pack["flashcards"]), quiz=json.loads(pack["quiz"]),
                           translating=translating)


@app.route("/api/translate/<int:file_id>", methods=["POST"])
def api_translate(file_id):
    if not request.is_json:
        abort(415)
    try:
        study.translate_pack(conn(), get_provider(), file_id, g.lang)
    except LookupError:
        abort(404)
    except DailyLimitReached as exc:
        log.warning("translate %s -> %s: daily limit: %s", file_id, g.lang, exc)
        return jsonify(error=T("err.ai_quota")), 429
    except AIError as exc:
        log.error("translate %s -> %s failed: %s", file_id, g.lang, exc)
        return jsonify(error=T("err.ai")), 502
    return jsonify(ok=True)


@app.route("/grades")
def grades():
    items = [d | {"pct": grade_percent(d["grade"])} for d in all_assignments()]
    items.sort(key=lambda d: (d["course"], d["due_date"] or ""))
    pcts = [d["pct"] for d in items if d["pct"] is not None]
    summary = {
        "avg": round(sum(pcts) / len(pcts)) if pcts else None,
        "graded": len(pcts),
        "done": sum(d["state"] == "done" for d in items),
        "total": len(items),
    }
    return render_template("grades.html", items=items, summary=summary)


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
                           selected=request.args.get("course", type=int))


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
        provider = get_provider()
        try:
            result = ask(provider)
        except DailyLimitReached:
            raise
        except AIError as exc:  # transient provider hiccup: one retry after a short pause
            log.warning("ask failed, retrying once: %s", exc)
            time.sleep(2)
            result = ask(provider)
    except DailyLimitReached as exc:
        log.warning("ask: daily limit: %s", exc)
        return jsonify(error=T("err.ai_quota")), 429
    except AIError as exc:
        log.error("ask failed after retry: %s", exc)
        return jsonify(error=T("err.ai")), 502
    except Exception:  # never show a traceback to the page; details go to the log only
        log.exception("ask crashed")
        return jsonify(error=T("err.ai")), 500
    return jsonify(result)


@app.route("/file/<int:file_id>")
def file_view(file_id):
    row = conn().execute("SELECT path, filename FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        abort(404)
    path = Path(row["path"]).resolve()
    if not path.is_relative_to(FILES_DIR) or not path.is_file():
        abort(404)
    return send_file(path, download_name=row["filename"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=5050)
    args = ap.parse_args()
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
