"""Sync one student's eClass data into Postgres through their own eClass session.

Reuses the Mac version's page parsers (eclass/courses.py, activities.py, files.py). Course content is shared per
course; deadlines, submission status and grades are the student's own. Files are downloaded into memory only to
read their text (for search and the AI chat), then dropped; students open files through /file/<id>.

    python -m web.sync --all      # background sync of students who opted in (milestone 4)
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from eclass.activities import parse_activity, parse_assign, pluginfile_links, resolve_url
from eclass.auth import EClassClient, EClassError, NetworkError, PageError, ServerError, SessionExpired
from eclass.config import ECLASS_URL, env_int
from eclass.courses import list_courses, parse_course_page
from eclass.extract import extract_bytes, method_for
from eclass.files import filename_from_response
from eclass.notify import parse_due
from web import eclass_login
from web.models import Activity, Course, Enrollment, Material, MaterialPage, Section, SyncRun, UserAssignment
from web.redact import redact

log = logging.getLogger("web.sync")
MAX_FILE_BYTES = env_int("SYNC_MAX_FILE_MB", 30) * 1024 * 1024  # bigger files (textbooks): link only, no text
LOCK_NAMESPACE = 7141  # pg advisory lock (namespace, user_id): one sync per student at a time
STALE_RUN = timedelta(minutes=30)  # a "running" sync older than this died without finishing
ECLASS_HOST = urlparse(ECLASS_URL).netloc


class SyncStats:
    def __init__(self):
        self.new_items = 0
        self.errors = 0


def _now():
    return datetime.now(timezone.utc)


def _name_from_url(url: str) -> str:
    return unquote(urlparse(url).path.rsplit("/", 1)[-1]) or "file"


# ---------------------------------------------------------------- files

def _read(resp) -> bytes | None:
    """The response body, or None when it is larger than MAX_FILE_BYTES (reading stops there)."""
    chunks, total = [], 0
    for chunk in resp.iter_content(64 * 1024):
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_FILE_BYTES:
            return None
    return b"".join(chunks)


def store_file(db: Session, activity_id: int, resp, name: str | None = None) -> bool:
    """Record a file from an eClass response and read its text; True when it is new or changed.

    An unchanged file (same size as last time, text already read) is not downloaded again.
    """
    try:
        name = name or filename_from_response(resp)
        size = int(resp.headers.get("Content-Length") or 0) or None
        material = db.scalar(select(Material).where(Material.activity_id == activity_id, Material.filename == name))
        is_new = material is None
        if is_new:
            material = Material(activity_id=activity_id, filename=name, eclass_url=resp.url)
            db.add(material)
        material.eclass_url = resp.url
        material.mimetype = (resp.headers.get("Content-Type") or "").split(";")[0][:120] or None
        if not is_new and material.extracted_at and size and size == material.size:
            return False
        data = None if size and size > MAX_FILE_BYTES else _read(resp)
    finally:
        resp.close()
    if data is None:
        material.size, material.extract_error = size, "too large to read"
        return is_new
    digest = hashlib.sha256(data).hexdigest()
    material.size = len(data)
    if not is_new and digest == material.sha256 and material.extracted_at:
        return False
    material.sha256, material.extracted_at, material.extract_error = digest, _now(), None
    db.flush()
    db.execute(delete(MaterialPage).where(MaterialPage.material_id == material.id))
    if method_for(name) is None:  # images, archives...: listed and downloadable, but no text
        material.n_pages = material.n_chars = 0
        return True
    try:
        pages, _method = extract_bytes(data, name)
    except Exception as exc:  # a corrupt or protected file must not stop the sync
        material.extract_error = type(exc).__name__
        return True
    db.add_all(MaterialPage(material_id=material.id, page=i, text=t) for i, t in enumerate(pages, 1) if t.strip())
    material.n_pages, material.n_chars = len(pages), sum(len(t) for t in pages)
    return True


def _store_links(db, client, activity_id: int, urls: list[str]) -> int:
    return sum(store_file(db, activity_id, client.get(url, stream=True), _name_from_url(url)) for url in urls)


def _ubfile(db, client, activity: Activity) -> int:
    """ubfile view.php redirects straight to the file, or (rarely) to a page of links."""
    resp = client.get(activity.url, stream=True)
    is_page = "pluginfile.php" not in resp.url and resp.headers.get("Content-Type", "").startswith("text/html")
    if not is_page:
        return int(store_file(db, activity.id, resp))
    soup = BeautifulSoup(resp.text, "html.parser")
    resp.close()
    return _store_links(db, client, activity.id, pluginfile_links(soup))


# ---------------------------------------------------------------- courses

def _upsert(db: Session, model, key: dict, values: dict):
    """(row, created): insert, or update the given columns of the existing row."""
    row = db.get(model, tuple(key.values()) if len(key) > 1 else next(iter(key.values())))
    if row is None:
        row = model(**key, **values)
        db.add(row)
        return row, True
    for field, value in values.items():
        setattr(row, field, value)
    return row, False


def _external_url(db: Session, client, act: dict) -> str | None:
    """url activities: store where they point (videos); resolved once, then reused."""
    known = db.get(Activity, act["id"])
    if known and known.url and urlparse(known.url).netloc not in ("", ECLASS_HOST):
        return known.url
    return resolve_url(client, act["url"]) or act["url"]


def sync_course(db: Session, client, user_id: int, course: dict, stats: SyncStats) -> None:
    sections = parse_course_page(client.soup(f"/course/view.php?id={course['id']}"))
    for section in sections:
        _upsert(db, Section, {"course_id": course["id"], "number": section["number"]}, {"name": section["name"]})
        db.flush()
        for li in section["activities"]:
            act = parse_activity(li, course["id"], section["number"])
            if act is None:
                continue
            try:
                if act["type"] == "url" and act["url"]:
                    act["url"] = _external_url(db, client, act)
                activity, created = _upsert(db, Activity, {"id": act["id"]}, {
                    "course_id": course["id"], "section": act["section"], "type": act["type"], "name": act["name"],
                    "url": act["url"], "last_seen_at": _now()})
                db.flush()
                changed = 0
                if activity.url and act["type"] == "ubfile":
                    changed = _ubfile(db, client, activity)
                elif activity.url and act["type"] == "folder":
                    changed = _store_links(db, client, activity.id, pluginfile_links(client.soup(activity.url)))
                elif activity.url and act["type"] == "assign":
                    info, attachments = parse_assign(client.soup(activity.url))
                    activity.intro = info.pop("intro")
                    _upsert(db, UserAssignment, {"user_id": user_id, "activity_id": activity.id}, {
                        "due_text": info["due_date"], "due_at": parse_due(info["due_date"]),
                        "submission_status": info["submission_status"], "grading_status": info["grading_status"],
                        "grade": info["grade"]})
                    _store_links(db, client, activity.id, attachments)
                # a new activity counts once; a new or changed file in a known activity counts per file
                stats.new_items += 1 if created else changed
                db.commit()
            except (NetworkError, ServerError, PageError, OSError) as exc:  # one broken activity: note, go on
                db.rollback()
                stats.errors += 1
                log.warning("activity %s of course %s failed: %s", act["id"], course["id"], type(exc).__name__)


def _sync(db: Session, client, user_id: int, stats: SyncStats) -> None:
    courses = list_courses(client)
    if not courses:  # signed in, but no course cards: the page layout probably changed
        raise PageError("no courses found on the eClass dashboard")
    for course in courses:
        _upsert(db, Course, {"id": course["id"]}, {"name": course["name"], "code": course["code"],
                                                  "professor": course["professor"], "last_seen_at": _now()})
    db.flush()
    for course in courses:
        _upsert(db, Enrollment, {"user_id": user_id, "course_id": course["id"]}, {"last_seen_at": _now()})
    db.execute(delete(Enrollment).where(Enrollment.user_id == user_id,  # courses the student no longer has
                                        Enrollment.course_id.not_in([c["id"] for c in courses])))
    db.commit()
    failed = []
    for course in courses:
        try:
            sync_course(db, client, user_id, course, stats)
        except (NetworkError, ServerError, PageError) as exc:  # one slow or broken course must not cost the others
            db.rollback()
            stats.errors += 1
            failed.append(exc)
            log.warning("course %s skipped: %s", course["id"], exc.code)
    if failed and len(failed) == len(courses):
        raise failed[0]


# ---------------------------------------------------------------- one run

def sync_user(engine, sessions: sessionmaker, user_id: int, trigger: str, client=None) -> SyncRun | None:
    """Sync one student; returns the finished run, or None when a sync of this student is already running."""
    with engine.connect() as lock:
        args = {"ns": LOCK_NAMESPACE, "uid": user_id}
        if not lock.execute(text("SELECT pg_try_advisory_lock(:ns, :uid)"), args).scalar():
            return None
        try:
            return _run(sessions, user_id, trigger, client)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:ns, :uid)"), args)


def _run(sessions: sessionmaker, user_id: int, trigger: str, client) -> SyncRun:
    stats = SyncStats()
    with sessions() as db:
        run = SyncRun(user_id=user_id, trigger=trigger)
        db.add(run)
        db.commit()
        try:
            if client is None:
                cookies = eclass_login.load_session(db, user_id)
                db.commit()
                if cookies is None:
                    raise SessionExpired("no live eClass session")
                client = EClassClient(cookies=cookies)
            _sync(db, client, user_id, stats)
            run.status = "done"
        except EClassError as exc:
            db.rollback()
            if isinstance(exc, SessionExpired):  # the saved session no longer works: forget it
                eclass_login.drop_session(db, user_id)
            run.status, run.error_code, run.error_summary = "error", exc.code, redact(str(exc))[:300]
            log.info("sync of user %s failed: %s", user_id, exc.code)
        except Exception as exc:
            db.rollback()
            run.status, run.error_code = "error", "other"
            run.error_summary = redact(f"{type(exc).__name__}: {exc}")[:300]
            log.exception("sync of user %s crashed", user_id)
        run.finished_at, run.new_items, run.errors = _now(), stats.new_items, stats.errors
        db.add(run)
        db.commit()
        return run


def latest_run(db: Session, user_id: int) -> SyncRun | None:
    return db.scalar(select(SyncRun).where(SyncRun.user_id == user_id).order_by(SyncRun.id.desc()).limit(1))


def is_running(db: Session, user_id: int) -> bool:
    return bool(db.scalar(select(func.count()).select_from(SyncRun).where(
        SyncRun.user_id == user_id, SyncRun.status == "running", SyncRun.started_at > _now() - STALE_RUN)))
