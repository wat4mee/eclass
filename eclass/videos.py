"""YouTube lecture videos (url activities): fetch the transcript and store it as a virtual file.

The transcript becomes a files row with path "youtube:<id>" plus extracted "pages" of ~3000
characters that start with their timestamp, so study packs, Q&A search and the study page treat a
lecture video like any other material. Non-YouTube links are skipped.
"""
import hashlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from . import db

PAGE_CHARS = 3000
RETRY_AFTER = timedelta(days=7)  # a video without a transcript is checked again after a week
LANGUAGES = ["en", "uz", "ru"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    activity_id  INTEGER PRIMARY KEY REFERENCES activities(id) ON DELETE CASCADE,
    video_id     TEXT,
    status       TEXT NOT NULL,       -- ok | none (no transcript) | not_youtube
    file_id      INTEGER,             -- the transcript's files row when status = ok
    detail       TEXT,
    checked_at   TEXT NOT NULL
);
"""


def youtube_id(url):
    u = urlparse(url or "")
    host = u.netloc.lower().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        return u.path.strip("/").split("/")[0] or None
    if host.endswith("youtube.com"):
        if u.path == "/watch":
            return parse_qs(u.query).get("v", [None])[0]
        m = re.match(r"/(embed|shorts|live)/([\w-]{6,})", u.path)
        return m.group(2) if m else None
    return None


def _stamp(seconds):
    s = int(seconds)
    return f"[{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}]" if s >= 3600 else f"[{s // 60:02d}:{s % 60:02d}]"


def to_pages(snippets):
    """Group transcript snippets into ~PAGE_CHARS pages, each starting with its timestamp."""
    pages, parts, start = [], [], None
    for sn in snippets:
        text = " ".join(sn.text.split())
        if not text:
            continue
        if start is None:
            start = sn.start
        parts.append(text)
        if sum(len(p) + 1 for p in parts) >= PAGE_CHARS:
            pages.append(f"{_stamp(start)} {' '.join(parts)}")
            parts, start = [], None
    if parts:
        pages.append(f"{_stamp(start)} {' '.join(parts)}")
    return pages


def fetch_transcript(video_id):
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    try:
        return api.fetch(video_id, languages=LANGUAGES).snippets
    except Exception as first:
        try:  # fall back to whatever transcript the video has
            return next(iter(api.list(video_id))).fetch().snippets
        except Exception:
            raise first from None


def _record(conn, activity_id, video_id, status, file_id=None, detail=None):
    conn.execute(
        """INSERT OR REPLACE INTO videos (activity_id, video_id, status, file_id, detail, checked_at)
           VALUES (?, ?, ?, ?, ?, ?)""", (activity_id, video_id, status, file_id, detail, db.now()))
    conn.commit()


def process(conn, log=print):
    """Fetch transcripts for url activities that have none yet. Returns outcome counts."""
    conn.executescript(SCHEMA)
    cutoff = (datetime.now(timezone.utc) - RETRY_AFTER).isoformat(timespec="seconds")
    rows = conn.execute(
        """SELECT a.id, a.name, a.url FROM activities a LEFT JOIN videos v ON v.activity_id = a.id
           WHERE a.type = 'url' AND (v.activity_id IS NULL OR (v.status = 'none' AND v.checked_at < ?))""",
        (cutoff,)).fetchall()
    stats = {"transcripts": 0, "unavailable": 0, "not_youtube": 0}
    for a in rows:
        vid = youtube_id(a["url"])
        if not vid:
            _record(conn, a["id"], None, "not_youtube")
            stats["not_youtube"] += 1
            continue
        try:
            pages = to_pages(fetch_transcript(vid))
            if not pages:
                raise ValueError("empty transcript")
        except Exception as exc:  # no captions, private video, blocked request...
            _record(conn, a["id"], vid, "none", detail=type(exc).__name__)
            stats["unavailable"] += 1
            log(f"  no transcript: {a['name']} ({type(exc).__name__})")
            continue
        text = "\n".join(pages)
        sha = hashlib.sha256(text.encode()).hexdigest()
        filename = f"{a['name']} — transcript"
        db.upsert_file(conn, a["id"], filename, f"youtube:{vid}", sha, len(text.encode()), a["url"])
        file_id = conn.execute("SELECT id FROM files WHERE activity_id = ? AND filename = ?",
                               (a["id"], filename)).fetchone()[0]
        db.save_extraction(conn, file_id, sha, "youtube", pages)
        _record(conn, a["id"], vid, "ok", file_id)
        stats["transcripts"] += 1
        log(f"  transcript: {a['name']} ({len(pages)} pages, {len(text)} chars)")
    return stats


def for_course(conn, course_id: int) -> dict:
    """{activity_id: {status, file_id, has_study}} for one course's videos, in a single query."""
    conn.executescript(SCHEMA)
    rows = conn.execute(
        """SELECT v.activity_id, v.status, v.file_id,
                  EXISTS (SELECT 1 FROM study s JOIN files f ON f.id = s.file_id AND f.sha256 = s.sha256
                          WHERE f.id = v.file_id) AS has_study
           FROM videos v JOIN activities a ON a.id = v.activity_id WHERE a.course_id = ?""", (course_id,))
    return {r["activity_id"]: {"status": r["status"], "file_id": r["file_id"], "has_study": bool(r["has_study"])}
            for r in rows}
