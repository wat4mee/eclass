"""Textbooks: split into chapters (PDF table of contents, else 30-page blocks) with one study pack each.

A book is any extracted file longer than study.MAX_AI_CHARS. Chapters are detected once per file
version; a chapter's pack is generated only on request and never regenerated.
"""
import json
import math
import re

from . import db, study

FRONT_MATTER = re.compile(
    r"cover|contents|preface|tribute|about the author|title page|copyright|dedication|acknowledg|"
    r"technology in|to the student|diagnostic test|^index|glossary|bibliograph|credits|answers to|"
    r"reference page|halftitle|half title", re.I)
MAX_PAGES = 60   # longer chapters are split into parts
BLOCK = 30       # pages per part / per block when there is no table of contents

SCHEMA = """
CREATE TABLE IF NOT EXISTS chapters (
    file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    sha256      TEXT NOT NULL,
    title       TEXT NOT NULL,
    start_page  INTEGER NOT NULL,
    end_page    INTEGER NOT NULL,
    summary     TEXT,                 -- the pack: NULL until generated
    concepts    TEXT,
    flashcards  TEXT,
    quiz        TEXT,
    language    TEXT,
    provider    TEXT,
    model       TEXT,
    created_at  TEXT,
    PRIMARY KEY (file_id, idx)
);
"""


def is_book(n_chars):
    return (n_chars or 0) > study.MAX_AI_CHARS


def _split(title, start, end):
    pages = end - start + 1
    if pages <= MAX_PAGES:
        return [(title, start, end)]
    parts = math.ceil(pages / BLOCK)
    size = math.ceil(pages / parts)
    return [(f"{title} ({k + 1}/{parts})", start + k * size, min(end, start + (k + 1) * size - 1))
            for k in range(parts)]


def detect(path, n_pages):
    """[(title, first_page, last_page)]; title is None for plain page blocks."""
    try:
        import pymupdf

        with pymupdf.open(path) as doc:
            toc = doc.get_toc()
    except Exception:
        toc = []
    starts = [(" ".join(re.sub(r"[\x00-\x1f]", " ", t[1]).split()), t[2])
              for t in toc if t[0] == 1 and 1 <= t[2] <= n_pages]
    found = []
    for i, (title, start) in enumerate(starts):
        end = starts[i + 1][1] - 1 if i + 1 < len(starts) else n_pages
        if end >= start and not FRONT_MATTER.search(title):
            found.append((title, start, end))
    if len(found) < 3:  # no usable table of contents
        found = [(None, a, min(n_pages, a + BLOCK - 1)) for a in range(1, n_pages + 1, BLOCK)]
    out = []
    for title, start, end in found:
        out.extend(_split(title, start, end) if title else [(None, start, end)])
    return out


def ensure(conn, file_row):
    """Chapters for the current version of a book file, detecting them on first use."""
    conn.executescript(SCHEMA)
    rows = conn.execute("SELECT * FROM chapters WHERE file_id = ? AND sha256 = ? ORDER BY idx",
                        (file_row["id"], file_row["sha256"])).fetchall()
    if rows:
        return rows
    n_pages = conn.execute("SELECT n_pages FROM extractions WHERE file_id = ?", (file_row["id"],)).fetchone()[0]
    conn.execute("DELETE FROM chapters WHERE file_id = ?", (file_row["id"],))
    conn.executemany(
        "INSERT INTO chapters (file_id, idx, sha256, title, start_page, end_page) VALUES (?, ?, ?, ?, ?, ?)",
        [(file_row["id"], i, file_row["sha256"], title or "", a, b)
         for i, (title, a, b) in enumerate(detect(file_row["path"], n_pages))])
    conn.commit()
    return conn.execute("SELECT * FROM chapters WHERE file_id = ? ORDER BY idx", (file_row["id"],)).fetchall()


def generate(conn, provider, file_id, idx, log=print):
    """Build and store the study pack of one chapter (no-op when it already exists)."""
    conn.executescript(SCHEMA)
    ch = conn.execute("SELECT * FROM chapters WHERE file_id = ? AND idx = ?", (file_id, idx)).fetchone()
    if ch is None:
        raise LookupError(f"no chapter {file_id}/{idx}")
    if ch["summary"]:
        return
    meta = conn.execute(
        """SELECT f.id, f.filename, f.sha256, a.name AS activity, c.name AS course
           FROM files f JOIN activities a ON a.id = f.activity_id JOIN courses c ON c.id = a.course_id
           WHERE f.id = ?""", (file_id,)).fetchone()
    title = ch["title"] or f"pages {ch['start_page']}-{ch['end_page']}"
    f = dict(meta) | {"activity": f"{meta['activity']}: {title}"}
    pages = [(r["page"], r["text"]) for r in conn.execute(
        "SELECT page, text FROM pages WHERE file_id = ? AND page BETWEEN ? AND ? AND text != '' ORDER BY page",
        (file_id, ch["start_page"], ch["end_page"]))]
    offset = (idx + 1) * 100_000  # keeps this chapter's resumable notes apart from other chapters
    code, result = study.build_pack(conn, provider, f, pages, log, notes_offset=offset)
    conn.execute(
        """UPDATE chapters SET summary = ?, concepts = ?, flashcards = ?, quiz = ?, language = ?, provider = ?,
               model = ?, created_at = ? WHERE file_id = ? AND idx = ?""",
        (result["summary"], json.dumps(result["key_concepts"], ensure_ascii=False),
         json.dumps(result["flashcards"], ensure_ascii=False), json.dumps(result["quiz"], ensure_ascii=False),
         code, provider.name, provider.model, db.now(), file_id, idx))
    conn.execute("DELETE FROM study_notes WHERE file_id = ? AND chunk >= ? AND chunk < ?",
                 (file_id, offset, offset + 100_000))
    conn.commit()
