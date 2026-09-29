"""Global search (Cmd+K): SQLite FTS5 over courses, assignments, files, study packs and chapters.

The index is small (hundreds of rows) and rebuilt whenever the underlying data changes.
"""
import html
import json
import re


SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
    kind UNINDEXED, ref UNINDEXED, course_id UNINDEXED, title, body,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""
_signature = None  # what the index was built from, per process


def _pack_text(summary, concepts, flashcards=None):
    parts = [summary or ""]
    parts += [f"{c['term']} {c['explanation']}" for c in json.loads(concepts or "[]")]
    parts += [f"{c['front']} {c['back']}" for c in json.loads(flashcards or "[]")]
    return " ".join(parts)


def rebuild(conn):
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM search_fts")
    rows = [("course", c["id"], c["id"], c["name"], f"{c['code'] or ''} {c['professor'] or ''}")
            for c in conn.execute("SELECT id, name, code, professor FROM courses")]
    rows += [("assign" if a["type"] == "assign" else "activity", a["id"], a["course_id"], a["name"], a["intro"] or "")
             for a in conn.execute(
                 """SELECT a.id, a.course_id, a.name, a.type, s.intro FROM activities a
                    LEFT JOIN assignments s ON s.activity_id = a.id WHERE a.type IN ('assign', 'url', 'ubboard')""")]
    rows += [("file", f["id"], f["course_id"], f["activity"], f["filename"])
             for f in conn.execute(
                 """SELECT f.id, a.course_id, a.name AS activity, f.filename FROM files f
                    JOIN activities a ON a.id = f.activity_id WHERE f.path NOT LIKE 'youtube:%'""")]
    rows += [("study", s["file_id"], s["course_id"], s["name"], _pack_text(s["summary"], s["concepts"], s["flashcards"]))
             for s in conn.execute(
                 """SELECT s.file_id, a.course_id, a.name, s.summary, s.concepts, s.flashcards FROM study s
                    JOIN files f ON f.id = s.file_id JOIN activities a ON a.id = f.activity_id""")]
    rows += [("chapter", f"{ch['file_id']}/{ch['idx']}", ch["course_id"], ch["title"] or ch["activity"],
              _pack_text(ch["summary"], ch["concepts"]))
             for ch in conn.execute(
                 """SELECT ch.*, a.course_id, a.name AS activity FROM chapters ch JOIN files f ON f.id = ch.file_id
                    JOIN activities a ON a.id = f.activity_id WHERE ch.summary IS NOT NULL""")]
    conn.executemany("INSERT INTO search_fts (kind, ref, course_id, title, body) VALUES (?, ?, ?, ?, ?)", rows)
    conn.commit()


def ensure_fresh(conn):
    global _signature
    conn.executescript(SCHEMA)
    database = conn.execute("PRAGMA database_list").fetchone()["file"]  # one process may open several databases
    sig = (database,) + tuple(conn.execute(
        """SELECT (SELECT COUNT(*) FROM files), (SELECT MAX(id) FROM files), (SELECT COUNT(*) FROM activities),
                  (SELECT COUNT(*) FROM study), (SELECT MAX(created_at) FROM study),
                  (SELECT COUNT(*) FROM chapters WHERE summary IS NOT NULL),
                  (SELECT COUNT(*) FROM courses), (SELECT MAX(last_seen) FROM courses)""").fetchone())
    if sig != _signature:
        rebuild(conn)
        _signature = sig


def _marked(text):
    """Escape FTS output, then turn its \\x02...\\x03 match markers into <mark> tags."""
    return html.escape(text or "").replace("\x02", "<mark>").replace("\x03", "</mark>")


def query(conn, text, limit=24):
    """Prefix search, every word must match. Returns rows with HTML-safe highlighted title/snippet."""
    ensure_fresh(conn)
    words = re.findall(r"\w+", text.lower())[:8]
    if not words:
        return []
    match = " ".join(f'"{w}"*' for w in words)
    rows = conn.execute(
        """SELECT kind, ref, course_id, title,
                  highlight(search_fts, 3, char(2), char(3)) AS h_title,
                  snippet(search_fts, 4, char(2), char(3), '…', 14) AS h_body
           FROM search_fts WHERE search_fts MATCH ?
           ORDER BY bm25(search_fts, 0, 0, 0, 6.0, 1.0) LIMIT ?""", (match, limit)).fetchall()
    out, studied = [], {r["ref"] for r in rows if r["kind"] == "study"}
    for r in rows:
        if r["kind"] == "file" and r["ref"] in studied:  # the study pack result already covers this file
            continue
        out.append({"kind": r["kind"], "ref": r["ref"], "course_id": r["course_id"], "title": r["title"],
                    "title_html": _marked(r["h_title"]), "snippet_html": _marked(r["h_body"])})
    return out
