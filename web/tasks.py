"""Runs students' syncs in the background of the web process, one student at a time.

Sign-in and the "refresh" button answer at once; the sync is queued. One worker thread, never several: a small
instance (Render's free plan: 0.1 CPU, 512 MB) cannot read several students' PDFs at the same time, and a sync that
runs out of memory takes the whole site down with it. The Postgres advisory lock in web.sync still guarantees that a
student is never synced twice at once across processes (the website and the cron job).
"""
import gc
import logging
import queue
import threading

from flask import Flask

from web import sync

log = logging.getLogger("web.tasks")
_queue: "queue.Queue[tuple[Flask, int, str]]" = queue.Queue()
_waiting: set[int] = set()  # students queued or syncing in this process
_guard = threading.Lock()
_worker: threading.Thread | None = None


def start_sync(app: Flask, user_id: int, trigger: str) -> None:
    """Queue a sync of this student (nothing happens if one is already queued or running here)."""
    global _worker
    with _guard:
        if user_id in _waiting:
            return
        _waiting.add(user_id)
        _queue.put((app, user_id, trigger))
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, name="sync-worker", daemon=True)
            _worker.start()


def waiting(user_id: int) -> bool:
    """True while this student's sync is queued or running in this process."""
    return user_id in _waiting


def _work() -> None:
    while True:
        app, user_id, trigger = _queue.get()
        try:
            sync.sync_user(app.extensions["db_engine"], app.extensions["db_sessions"], user_id, trigger)
        except Exception:  # never let the worker die silently
            log.exception("background sync of user %s crashed", user_id)
        finally:
            with _guard:
                _waiting.discard(user_id)
            gc.collect()  # hand the memory of the files just read back before the next student
            _queue.task_done()
