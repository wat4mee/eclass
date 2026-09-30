"""Runs syncs in the background of the web process, one at a time.

Sign-in and the "refresh" button answer at once; the sync is queued. One worker thread, never several: a small
instance (Render's free plan: 0.1 CPU, 512 MB) cannot read several students' PDFs at the same time, and a sync that
runs out of memory takes the whole site down with it. The scheduled sync of every opted-in student
(POST /internal/sync-all) goes through the same worker; between two of its students the worker first serves
students waiting on the website. The Postgres advisory lock in web.sync still guarantees that a student is never
synced twice at once across processes.
"""
import gc
import logging
import queue
import threading
import time

from flask import Flask

from web import sync

log = logging.getLogger("web.tasks")
_queue: "queue.Queue[tuple[str, Flask, int | None, str]]" = queue.Queue()  # (kind, app, user id, trigger)
_waiting: set[int] = set()  # students queued or syncing in this process
_all_pending = False  # a sync of every opted-in student is queued or running
_guard = threading.Lock()
_worker: threading.Thread | None = None


def _ensure_worker() -> None:
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_work, name="sync-worker", daemon=True)
        _worker.start()


def start_sync(app: Flask, user_id: int, trigger: str) -> None:
    """Queue a sync of this student (nothing happens if one is already queued or running here)."""
    with _guard:
        if user_id in _waiting:
            return
        _waiting.add(user_id)
        _queue.put(("user", app, user_id, trigger))
        _ensure_worker()


def start_sync_all(app: Flask) -> bool:
    """Queue a sync of every student who opted into background sync; False if one is already queued or running."""
    global _all_pending
    with _guard:
        if _all_pending:
            return False
        _all_pending = True
        _queue.put(("all", app, None, "schedule"))
        _ensure_worker()
    return True


def waiting(user_id: int) -> bool:
    """True while this student's sync is queued or running in this process."""
    return user_id in _waiting


def _run(job) -> None:
    global _all_pending
    kind, app, user_id, trigger = job
    engine, sessions = app.extensions["db_engine"], app.extensions["db_sessions"]
    try:
        if kind == "user":
            sync.sync_user(engine, sessions, user_id, trigger)
        else:
            log.info("scheduled sync of all students: %s", sync.run_all(engine, sessions, sleep=_serve_waiting))
    except Exception:  # never let the worker die silently
        log.exception("background sync (%s %s) crashed", kind, user_id or "")
    finally:
        with _guard:
            if kind == "user":
                _waiting.discard(user_id)
            else:
                _all_pending = False
        gc.collect()  # hand the memory of the files just read back before the next sync


def _serve_waiting(seconds: float) -> None:
    """The pause between two students of a scheduled run: sync students waiting on the website first (a
    sign-in should not wait for the whole batch), then rest for whatever is left of the pause."""
    end = time.monotonic() + seconds
    while True:
        try:
            job = _queue.get_nowait()  # only single students: a second "all" job cannot be queued meanwhile
        except queue.Empty:
            break
        try:
            _run(job)
        finally:
            _queue.task_done()
    time.sleep(max(0.0, end - time.monotonic()))


def _work() -> None:
    while True:
        job = _queue.get()
        try:
            _run(job)
        finally:
            _queue.task_done()
