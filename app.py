"""eClass Companion dashboard - local only.

    python app.py            # http://127.0.0.1:5050
"""
import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, abort, g, jsonify, render_template, request, send_file

from eclass import db, rag
from eclass.ai import AIError, get_provider
from eclass.notify import is_submitted, parse_due

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "eclass.db"
FILES_DIR = (ROOT / "data" / "files").resolve()
ECLASS_URL = "https://eclass.inha.ac.kr"

app = Flask(__name__)


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

def human_delta(delta):
    minutes = int(delta.total_seconds() // 60)
    days, rem = divmod(minutes, 24 * 60)
    hours, mins = divmod(rem, 60)
    if days:
        return f"{days} kun {hours} soat"
    return f"{hours} soat {mins} daqiqa" if hours else f"{mins} daqiqa"


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
    return dict(row) | {
        "state": state,
        "due": due,
        "left": human_delta(due - now) if due and due > now else None,
    }


def grade_percent(grade):
    m = re.match(r"\s*([\d.]+)\s*/\s*([\d.]+)", grade or "")
    return round(100 * float(m.group(1)) / float(m.group(2))) if m and float(m.group(2)) else None


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
                  (SELECT COUNT(*) FROM activities a WHERE a.course_id = c.id AND a.type = 'assign') AS n_assign
           FROM courses c ORDER BY c.name""").fetchall()


@app.context_processor
def _globals():
    last = conn().execute("SELECT MAX(last_seen) AS t FROM courses").fetchone()["t"]
    synced = datetime.fromisoformat(last).astimezone().strftime("%d.%m %H:%M") if last else "—"
    return {"nav_courses": courses(), "last_sync": synced, "eclass_url": ECLASS_URL}


@app.template_filter("size")
def _size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


@app.template_filter("dt")
def _dt(value):
    return value.strftime("%d.%m %H:%M") if value else "—"


# ---------------------------------------------------------------- pages

@app.route("/")
def index():
    items = all_assignments()
    pending = [d for d in items if d["state"] != "done"]
    graded = [d | {"pct": grade_percent(d["grade"])} for d in items if d["grade"]]
    materials = conn().execute(
        """SELECT f.id, f.filename, f.downloaded_at, a.name AS activity, c.id AS course_id,
                  c.name AS course, (s.file_id IS NOT NULL) AS has_study
           FROM files f JOIN activities a ON a.id = f.activity_id JOIN courses c ON c.id = a.course_id
           LEFT JOIN study s ON s.file_id = f.id AND s.sha256 = f.sha256
           WHERE a.type != 'assign' ORDER BY f.downloaded_at DESC, f.id DESC LIMIT 8""").fetchall()
    return render_template("index.html", pending=pending, graded=graded, materials=materials,
                           course_list=courses())


@app.route("/course/<int:course_id>")
def course(course_id):
    c = conn()
    info = c.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    if info is None:
        abort(404)
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
    weeks = [(s, by_section[s["number"]]) for s in sections if by_section.get(s["number"])]
    return render_template("course.html", course=info, weeks=weeks, files=files, assigns=assigns)


@app.route("/study/<int:file_id>")
def study_page(file_id):
    row = conn().execute(
        """SELECT s.*, f.filename, a.name AS activity, c.id AS course_id, c.name AS course
           FROM study s JOIN files f ON f.id = s.file_id JOIN activities a ON a.id = f.activity_id
           JOIN courses c ON c.id = a.course_id WHERE s.file_id = ?""", (file_id,)).fetchone()
    if row is None:
        abort(404)
    return render_template("study.html", s=row, concepts=json.loads(row["concepts"]),
                           flashcards=json.loads(row["flashcards"]), quiz=json.loads(row["quiz"]))


@app.route("/grades")
def grades():
    items = [d | {"pct": grade_percent(d["grade"])} for d in all_assignments()]
    items.sort(key=lambda d: (d["course"], d["due_date"] or ""))
    return render_template("grades.html", items=items)


@app.route("/ask")
def ask_page():
    return render_template("ask.html", course_list=courses(), selected=request.args.get("course", type=int))


@app.route("/api/ask", methods=["POST"])
def api_ask():
    # JSON only: a cross-site form cannot send application/json without a CORS preflight
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(415)
    question = str(data.get("question", "")).strip()
    if not question or len(question) > 1000:
        return jsonify(error="Savol bo'sh yoki juda uzun (1000 belgigacha)."), 400
    course_id = data.get("course_id") or None
    try:
        result = rag.answer(conn(), get_provider(), question,
                            course_id=int(course_id) if course_id else None)
    except AIError as exc:
        return jsonify(error=f"AI xatosi: {exc}"), 502
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
