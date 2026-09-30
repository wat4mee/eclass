"""Milestone 3: syncing a student from (fake) eClass into Postgres."""
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text

from eclass.auth import PageError
from web import eclass_login, sync, tasks, users
from web.models import (Activity, Course, EClassSession, Enrollment, Material, MaterialPage, SyncRun,
                        UserAssignment)
from tests.web.fake_eclass import YOUTUBE, FakeSite


@pytest.fixture
def world(app):
    """(run(user, site), sessions, make_user) on the test database."""
    engine, sessions = app.extensions["db_engine"], app.extensions["db_sessions"]

    def make_user(name="u2410001"):
        with sessions() as db:
            user = users.signed_in(db, name)
            db.commit()
            return user.id

    def run(user_id, site=None, trigger="login"):
        return sync.sync_user(engine, sessions, user_id, trigger, site or FakeSite())
    return run, sessions, make_user


def count(sessions, model, **where):
    with sessions() as db:
        return db.scalar(select(func.count()).select_from(model).filter_by(**where))


def test_first_sync_stores_courses_content_and_personal_data(world):
    run, sessions, make_user = world
    uid = make_user()
    result = run(uid)
    assert (result.status, result.errors) == ("done", 0) and result.new_items >= 4
    with sessions() as db:
        assert {c.id for c in db.scalars(select(Course))} == {2539, 2562}
        assert count(sessions, Enrollment, user_id=uid) == 2
        assert {a.id for a in db.scalars(select(Activity))} == {701, 702, 703, 704}  # the label has no page
        assert db.get(Activity, 702).url == YOUTUBE
        mine = db.get(UserAssignment, (uid, 703))
        assert mine.grade == "22.00 / 25.00" and mine.due_at.tzinfo is not None
        assert db.get(Activity, 703).intro.startswith("Solve problems 1-10")
        files = {m.filename: m for m in db.scalars(select(Material))}
        assert set(files) == {"lecture3.pdf", "hw1.pdf", "data set.xlsx", "reading1.pdf"}
        assert files["lecture3.pdf"].eclass_url.endswith("/pluginfile.php/1/mod_ubfile/content/0/lecture3.pdf")
        assert files["lecture3.pdf"].n_pages == 1 and files["data set.xlsx"].n_pages == 0
        text_ = db.scalar(select(MaterialPage.text).where(MaterialPage.material_id == files["lecture3.pdf"].id))
        assert "Derivatives measure the rate of change" in text_


def test_a_second_sync_changes_nothing_and_downloads_nothing_again(world):
    run, sessions, make_user = world
    uid = make_user()
    run(uid)
    before = [count(sessions, m) for m in (Course, Activity, Material, MaterialPage, UserAssignment)]
    site = FakeSite()
    result = run(uid, site)
    assert [count(sessions, m) for m in (Course, Activity, Material, MaterialPage, UserAssignment)] == before
    assert result.new_items == 0
    assert [u for u in site.downloaded() if u.endswith(".pdf")] == []  # same size, text already read


def test_classmates_share_course_content_but_not_grades(world):
    run, sessions, make_user = world
    first, second = make_user("u2410001"), make_user("u2410002")
    run(first)
    materials = count(sessions, Material)
    site = FakeSite()
    run(second, site)
    assert count(sessions, Material) == materials  # stored once per course
    assert [u for u in site.downloaded() if u.endswith(".pdf")] == []  # the classmate's sync read them already
    assert count(sessions, UserAssignment, user_id=first) == count(sessions, UserAssignment, user_id=second) == 1


def test_an_expired_session_is_reported_and_forgotten(world):
    run, sessions, make_user = world
    uid = make_user()
    with sessions() as db:
        eclass_login.save_session(db, uid, [{"name": "MoodleSession", "value": "x"}], 120)
        db.commit()
    result = run(uid, FakeSite(expired=True))
    assert (result.status, result.error_code) == ("error", "session")
    assert count(sessions, EClassSession, user_id=uid) == 0


def test_without_a_saved_session_the_sync_asks_for_a_new_sign_in(world, app):
    _, sessions, make_user = world
    uid = make_user()
    result = sync.sync_user(app.extensions["db_engine"], sessions, uid, "button")  # no client: needs a saved session
    assert (result.status, result.error_code) == ("error", "session")


def test_one_broken_course_does_not_stop_the_others(world):
    run, sessions, make_user = world
    uid = make_user()
    result = run(uid, FakeSite(broken={2562}))
    assert (result.status, result.errors) == ("done", 1)
    assert count(sessions, Material) == 4


def test_a_dropped_course_disappears_from_the_student(world):
    run, sessions, make_user = world
    uid = make_user()
    run(uid)
    run(uid, FakeSite(courses={2539}))
    with sessions() as db:
        assert [e.course_id for e in db.scalars(select(Enrollment).where(Enrollment.user_id == uid))] == [2539]


def test_error_details_are_redacted(world):
    run, sessions, make_user = world
    uid = make_user()
    result = run(uid, FakeSite(fail=PageError("unexpected page for password=hunter2")))
    assert result.status == "error" and "hunter2" not in result.error_summary


def test_one_sync_per_student_at_a_time(world, app, engine):
    _, sessions, make_user = world
    uid = make_user()
    with engine.connect() as other:  # another process is syncing this student
        other.execute(text("SELECT pg_advisory_lock(:ns, :uid)"), {"ns": sync.LOCK_NAMESPACE, "uid": uid})
        assert sync.sync_user(app.extensions["db_engine"], sessions, uid, "button", FakeSite()) is None
        other.execute(text("SELECT pg_advisory_unlock(:ns, :uid)"), {"ns": sync.LOCK_NAMESPACE, "uid": uid})
    assert count(sessions, SyncRun, user_id=uid) == 0


def test_a_run_that_died_is_not_shown_as_running_forever(world):
    _, sessions, make_user = world
    uid = make_user()
    with sessions() as db:
        db.add(SyncRun(user_id=uid, trigger="login", started_at=datetime.now(timezone.utc) - timedelta(hours=2)))
        db.commit()
        assert not sync.is_running(db, uid)


def test_running_means_a_live_process_holds_the_lock(world, engine):
    """A server restart (out of memory, redeploy) kills a sync mid-way: its run must not spin for half an hour."""
    _, sessions, make_user = world
    uid = make_user()
    with sessions() as db:
        db.add(SyncRun(user_id=uid, trigger="login"))  # started a second ago
        db.commit()
    with engine.connect() as other:  # the process running it is alive
        other.execute(text("SELECT pg_advisory_lock(:ns, :uid)"), {"ns": sync.LOCK_NAMESPACE, "uid": uid})
        with sessions() as db:
            assert sync.is_running(db, uid)
            sync.reap(db, uid)  # nothing to close while the lock is held
            assert db.scalar(select(SyncRun.status)) == "running"
        other.execute(text("SELECT pg_advisory_unlock(:ns, :uid)"), {"ns": sync.LOCK_NAMESPACE, "uid": uid})
    with sessions() as db:  # the process died: the lock went with it
        assert not sync.is_running(db, uid)
        sync.reap(db, uid)
        run = db.scalar(select(SyncRun))
        assert (run.status, run.error_code) == ("error", "stopped") and run.finished_at is not None


def test_the_status_page_closes_a_dead_run(client, app):
    from tests.web.conftest import sign_in
    client.get("/login?lang=en")
    sign_in(client)
    with app.extensions["db_sessions"]() as db:
        db.add(SyncRun(user_id=1, trigger="login"))
        db.commit()
    status = client.get("/sync/status").get_json()
    assert status["state"] == "error" and "stopped unexpectedly" in status["message"]


# ---------------------------------------------------------------- the web process's queue

REAL_START = tasks.start_sync  # the app fixture replaces it; these tests use the real queue


def test_syncs_run_one_at_a_time_and_are_never_queued_twice(app, monkeypatch):
    calls, active, peak = [], [0], [0]
    release = threading.Event()

    def fake_sync(engine, sessions, user_id, trigger):
        active[0] += 1
        peak[0] = max(peak[0], active[0])
        calls.append(user_id)
        release.wait(5)
        active[0] -= 1
    monkeypatch.setattr(tasks.sync, "sync_user", fake_sync)
    for user_id in (101, 102, 101, 103):  # 101 signs in twice while its sync is still queued or running
        REAL_START(app, user_id, "login")
    assert tasks.waiting(101) and tasks.waiting(103)
    release.set()
    tasks._queue.join()
    assert calls == [101, 102, 103] and peak[0] == 1
    assert not tasks.waiting(101) and not tasks.waiting(103)


def test_a_queued_student_is_told_so(client, app, monkeypatch):
    from tests.web.conftest import sign_in
    client.get("/login?lang=en")
    sign_in(client)
    monkeypatch.setattr(tasks, "_waiting", {1})
    status = client.get("/sync/status").get_json()
    assert status["state"] == "running" and "You are in the queue" in status["message"]
    assert "You are in the queue" in client.get("/").get_data(as_text=True)
