"""Runs a student's sync in a background thread, so sign-in and the "refresh" button answer at once.

The Postgres advisory lock in web.sync makes sure one student is never synced twice at the same time, even across
processes (web workers and the cron job).
"""
import logging
import threading

from flask import Flask

from web import sync

log = logging.getLogger("web.tasks")


def start_sync(app: Flask, user_id: int, trigger: str) -> None:
    engine, sessions = app.extensions["db_engine"], app.extensions["db_sessions"]

    def run():
        try:
            sync.sync_user(engine, sessions, user_id, trigger)
        except Exception:  # never let a background thread die silently
            log.exception("background sync of user %s crashed", user_id)

    threading.Thread(target=run, name=f"sync-{user_id}", daemon=True).start()
