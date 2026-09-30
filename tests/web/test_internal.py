"""POST /internal/sync-all: the free scheduler (GitHub Actions) starts the background sync of every opted-in
student. No login or CSRF; a bearer token compared in constant time; off without CRON_SECRET; 1 call a minute."""
import logging
import threading

import pytest

from web import tasks

SECRET = "test-cron-secret-0123456789abcdef"
URL = "/internal/sync-all"
REAL_START = tasks.start_sync  # the app fixture replaces start_sync; the queue test uses the real one
REAL_START_ALL = tasks.start_sync_all


@pytest.fixture
def started(app, monkeypatch):
    """Records scheduled runs instead of starting them; the endpoint is configured with SECRET."""
    calls = []
    app.config["CRON_SECRET"] = SECRET
    monkeypatch.setattr(tasks, "start_sync_all", lambda a: calls.append(a) or True)
    return calls


def call(client, token=SECRET, scheme="Bearer"):
    headers = {"Authorization": f"{scheme} {token}"} if token is not None else {}
    return client.post(URL, headers=headers)


def test_the_right_token_starts_the_sync_without_login_or_csrf(client, started):
    resp = call(client)
    assert resp.status_code == 202 and resp.get_json() == {"status": "started"}
    assert len(started) == 1


@pytest.mark.parametrize("token, scheme", [("wrong-token-of-some-length-000000", "Bearer"), (SECRET[:-1], "Bearer"),
                                           (SECRET, "Basic"), ("", "Bearer")])
def test_a_wrong_token_is_refused_and_reveals_nothing(client, started, token, scheme):
    resp = call(client, token, scheme)
    assert resp.status_code == 401 and resp.get_json() == {"error": "unauthorized"}
    assert resp.headers["WWW-Authenticate"] == "Bearer" and started == []


def test_no_token_is_refused(client, started):
    resp = call(client, token=None)
    assert resp.status_code == 401 and started == []


@pytest.mark.parametrize("secret", ["", "too-short"])
def test_without_a_cron_secret_the_endpoint_is_off(client, app, started, secret):
    app.config["CRON_SECRET"] = secret
    resp = call(client, token=secret or "anything")
    assert resp.status_code == 503 and resp.get_json() == {"error": "not configured"} and started == []


def test_one_call_a_minute(client, started):
    assert call(client).status_code == 202
    assert call(client).status_code == 429  # a second call right away, even with the right token
    assert len(started) == 1


def test_guessing_counts_against_the_limit_too(client, started):
    assert call(client, "guess-number-one-000000000000000").status_code == 401
    assert call(client).status_code == 429


def test_a_run_already_going_is_not_started_twice(client, app, monkeypatch):
    app.config["CRON_SECRET"] = SECRET
    monkeypatch.setattr(tasks, "start_sync_all", lambda a: False)
    resp = call(client)
    assert resp.status_code == 202 and resp.get_json() == {"status": "already running"}


def test_calls_are_logged_without_the_token(client, started, caplog):
    caplog.set_level(logging.INFO)
    call(client)
    assert "sync-all accepted: started" in caplog.text and SECRET not in caplog.text


def test_only_post(client, started):
    assert client.get(URL, headers={"Authorization": f"Bearer {SECRET}"}).status_code == 405


# ---------------------------------------------------------------- the shared worker

def test_the_scheduled_run_shares_the_single_worker_and_lets_students_in(app, monkeypatch):
    """Never two syncs at once; a student signing in during the batch is served in the next pause."""
    order, release = [], threading.Event()

    def fake_run_all(engine, sessions, sleep):
        order.append("all: first student")
        release.wait(5)
        sleep(0)  # the pause between two students
        order.append("all: second student")
        return {}
    monkeypatch.setattr(tasks.sync, "run_all", fake_run_all)
    monkeypatch.setattr(tasks.sync, "sync_user", lambda engine, sessions, uid, trigger: order.append(f"user {uid}"))
    assert REAL_START_ALL(app) is True
    assert REAL_START_ALL(app) is False  # already queued or running
    REAL_START(app, 201, "login")  # a student signs in meanwhile
    release.set()
    tasks._queue.join()
    assert order == ["all: first student", "user 201", "all: second student"]
    assert REAL_START_ALL(app) is True  # finished: the next scheduled call starts a new run
    tasks._queue.join()
