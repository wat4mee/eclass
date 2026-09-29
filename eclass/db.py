"""SQLite storage for synced eClass data."""
import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    code        TEXT,
    professor   TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sections (
    course_id   INTEGER NOT NULL REFERENCES courses(id),
    number      INTEGER NOT NULL,
    name        TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    PRIMARY KEY (course_id, number)
);

CREATE TABLE IF NOT EXISTS activities (
    id          INTEGER PRIMARY KEY,          -- Moodle course-module id
    course_id   INTEGER NOT NULL REFERENCES courses(id),
    section     INTEGER,
    type        TEXT NOT NULL,
    name        TEXT,
    url         TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id   INTEGER NOT NULL REFERENCES activities(id),
    filename      TEXT NOT NULL,
    path          TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    size          INTEGER NOT NULL,
    downloaded_at TEXT NOT NULL,
    source_url    TEXT,
    UNIQUE (activity_id, filename)
);

CREATE TABLE IF NOT EXISTS assignments (
    activity_id       INTEGER PRIMARY KEY REFERENCES activities(id),
    due_date          TEXT,               -- as shown by eClass, e.g. '2026-09-25 15:00'
    submission_status TEXT,
    grading_status    TEXT,
    grade             TEXT,               -- e.g. '22.00 / 25.00'
    intro             TEXT,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    key      TEXT PRIMARY KEY,          -- e.g. 'grade:70927:22.00 / 25.00'
    sent_at  TEXT NOT NULL,
    seeded   INTEGER NOT NULL DEFAULT 0 -- 1 = marked as known on first run, never sent
);

CREATE TABLE IF NOT EXISTS extractions (
    file_id      INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    sha256       TEXT NOT NULL,         -- hash of the file the text came from
    method       TEXT NOT NULL,         -- pdf / pptx / docx
    n_pages      INTEGER NOT NULL,      -- pages / slides (1 for docx)
    n_chars      INTEGER NOT NULL,
    error        TEXT,
    extracted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pages (
    file_id  INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    page     INTEGER NOT NULL,          -- 1-based page / slide number
    text     TEXT NOT NULL,
    PRIMARY KEY (file_id, page)
);

CREATE TABLE IF NOT EXISTS study (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    sha256      TEXT NOT NULL,          -- file version the material was generated from
    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,
    language    TEXT NOT NULL,
    summary     TEXT NOT NULL,
    concepts    TEXT NOT NULL,          -- JSON [{term, explanation}]
    flashcards  TEXT NOT NULL,          -- JSON [{front, back}]
    quiz        TEXT NOT NULL,          -- JSON [{question, options[4], answer_index, explanation}]
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS study_notes (  -- map step for long files; lets a run resume mid-file
    file_id  INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    sha256   TEXT NOT NULL,
    chunk    INTEGER NOT NULL,
    notes    TEXT NOT NULL,
    PRIMARY KEY (file_id, sha256, chunk)
);

CREATE TABLE IF NOT EXISTS chunks (       -- retrieval units for course Q&A (stage 4)
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    sha256     TEXT NOT NULL,             -- file version the chunk was cut from
    page       INTEGER NOT NULL,
    text       TEXT NOT NULL,
    embedding  BLOB NOT NULL              -- float32[384], L2-normalized
);
CREATE INDEX IF NOT EXISTS chunks_file ON chunks(file_id);

-- keyword index; rowid = chunks.id
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, tokenize = 'porter unicode61');

CREATE TABLE IF NOT EXISTS progress (     -- materials the student marked as studied
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    studied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS study_i18n (   -- study packs translated for the dashboard language
    file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    language    TEXT NOT NULL,
    sha256      TEXT NOT NULL,            -- version of the source pack's file
    summary     TEXT NOT NULL,
    concepts    TEXT NOT NULL,
    flashcards  TEXT NOT NULL,
    quiz        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (file_id, language)
);

CREATE TABLE IF NOT EXISTS index_state (  -- progress per file, so long textbooks resume mid-way
    file_id    INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    sha256     TEXT NOT NULL,
    done_page  INTEGER NOT NULL,          -- pages <= done_page are chunked and embedded
    complete   INTEGER NOT NULL DEFAULT 0
);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path):
    conn = sqlite3.connect(path, timeout=30)  # wait for another writer instead of failing
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")  # readers (dashboard) never block the writer
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def upsert_course(conn, course):
    ts = now()
    cur = conn.execute(
        """INSERT INTO courses (id, name, code, professor, first_seen, last_seen)
           VALUES (:id, :name, :code, :professor, :ts, :ts)
           ON CONFLICT(id) DO UPDATE SET name=excluded.name, code=excluded.code,
               professor=excluded.professor, last_seen=excluded.last_seen
           RETURNING first_seen = last_seen AS is_new""",
        {**course, "ts": ts},
    )
    return bool(cur.fetchone()["is_new"])


def upsert_section(conn, course_id, number, name):
    ts = now()
    cur = conn.execute(
        """INSERT INTO sections (course_id, number, name, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(course_id, number) DO UPDATE SET name=excluded.name,
               last_seen=excluded.last_seen
           RETURNING first_seen = last_seen AS is_new""",
        (course_id, number, name, ts, ts),
    )
    return bool(cur.fetchone()["is_new"])


def upsert_activity(conn, act):
    """Insert or refresh an activity; returns True if it was not seen before."""
    ts = now()
    cur = conn.execute(
        """INSERT INTO activities (id, course_id, section, type, name, url, first_seen, last_seen)
           VALUES (:id, :course_id, :section, :type, :name, :url, :ts, :ts)
           ON CONFLICT(id) DO UPDATE SET course_id=excluded.course_id,
               section=excluded.section, type=excluded.type, name=excluded.name,
               url=excluded.url, last_seen=excluded.last_seen
           RETURNING first_seen = last_seen AS is_new""",
        {**act, "ts": ts},
    )
    return bool(cur.fetchone()["is_new"])


def get_files(conn, activity_id):
    return conn.execute(
        "SELECT * FROM files WHERE activity_id = ? ORDER BY filename", (activity_id,)
    ).fetchall()


def path_owner(conn, path):
    row = conn.execute("SELECT activity_id FROM files WHERE path = ?", (path,)).fetchone()
    return row["activity_id"] if row else None


def upsert_file(conn, activity_id, filename, path, sha256, size, source_url):
    conn.execute(
        """INSERT INTO files (activity_id, filename, path, sha256, size, downloaded_at, source_url)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(activity_id, filename) DO UPDATE SET path=excluded.path,
               sha256=excluded.sha256, size=excluded.size,
               downloaded_at=excluded.downloaded_at, source_url=excluded.source_url""",
        (activity_id, filename, path, sha256, size, now(), source_url),
    )


def upsert_assignment(conn, activity_id, info):
    """Store assignment details; returns the previous row (or None) for change detection."""
    prev = conn.execute(
        "SELECT * FROM assignments WHERE activity_id = ?", (activity_id,)
    ).fetchone()
    conn.execute(
        """INSERT INTO assignments (activity_id, due_date, submission_status,
               grading_status, grade, intro, updated_at)
           VALUES (:activity_id, :due_date, :submission_status, :grading_status,
               :grade, :intro, :ts)
           ON CONFLICT(activity_id) DO UPDATE SET due_date=excluded.due_date,
               submission_status=excluded.submission_status,
               grading_status=excluded.grading_status, grade=excluded.grade,
               intro=excluded.intro, updated_at=excluded.updated_at""",
        {"activity_id": activity_id, "ts": now(), **info},
    )
    return prev


def notified_keys(conn):
    return {row["key"] for row in conn.execute("SELECT key FROM notifications")}


def mark_notified(conn, keys, seeded=False):
    conn.executemany(
        "INSERT OR IGNORE INTO notifications (key, sent_at, seeded) VALUES (?, ?, ?)",
        [(k, now(), int(seeded)) for k in keys],
    )
    conn.commit()


def save_extraction(conn, file_id, sha256, method, pages, error=None):
    """Replace the stored text of a file; `pages` is a list of page texts."""
    conn.execute("DELETE FROM pages WHERE file_id = ?", (file_id,))
    conn.executemany(
        "INSERT INTO pages (file_id, page, text) VALUES (?, ?, ?)",
        [(file_id, i, text) for i, text in enumerate(pages, 1)],
    )
    conn.execute(
        """INSERT INTO extractions (file_id, sha256, method, n_pages, n_chars, error, extracted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(file_id) DO UPDATE SET sha256=excluded.sha256, method=excluded.method,
               n_pages=excluded.n_pages, n_chars=excluded.n_chars, error=excluded.error,
               extracted_at=excluded.extracted_at""",
        (file_id, sha256, method, len(pages), sum(len(t) for t in pages), error, now()),
    )
    conn.commit()


def save_study(conn, file_id, sha256, provider, model, language, result):
    conn.execute(
        """INSERT INTO study (file_id, sha256, provider, model, language, summary,
               concepts, flashcards, quiz, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(file_id) DO UPDATE SET sha256=excluded.sha256,
               provider=excluded.provider, model=excluded.model, language=excluded.language,
               summary=excluded.summary, concepts=excluded.concepts,
               flashcards=excluded.flashcards, quiz=excluded.quiz,
               created_at=excluded.created_at""",
        (file_id, sha256, provider, model, language, result["summary"],
         json.dumps(result["key_concepts"], ensure_ascii=False),
         json.dumps(result["flashcards"], ensure_ascii=False),
         json.dumps(result["quiz"], ensure_ascii=False), now()),
    )
    conn.execute("DELETE FROM study_notes WHERE file_id = ?", (file_id,))
    conn.commit()


def save_translation(conn, file_id, language, sha256, result):
    conn.execute(
        """INSERT OR REPLACE INTO study_i18n
               (file_id, language, sha256, summary, concepts, flashcards, quiz, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (file_id, language, sha256, result["summary"],
         json.dumps(result["key_concepts"], ensure_ascii=False),
         json.dumps(result["flashcards"], ensure_ascii=False),
         json.dumps(result["quiz"], ensure_ascii=False), now()),
    )
    conn.commit()
