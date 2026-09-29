"""Milestone 3: the student's pages, file streaming, refresh and reconnect (eClass faked)."""
from sqlalchemy import delete, select

from web import sync
from web.models import Activity, EClassSession, Enrollment, Material, User
from tests.web.conftest import FakeEClass, csrf_token, sign_in
from tests.web.fake_eclass import YOUTUBE, FakeSite


def synced(client, app, username="u2410001", site=None) -> int:
    """Sign in and run the first sync right away (in tests the background sync is only recorded)."""
    sign_in(client, username)
    with app.extensions["db_sessions"]() as db:
        uid = db.scalar(select(User.id).where(User.eclass_username == username))
    sync.sync_user(app.extensions["db_engine"], app.extensions["db_sessions"], uid, "login", site or FakeSite())
    return uid


def material_id(app, filename="lecture3.pdf") -> int:
    with app.extensions["db_sessions"]() as db:
        return db.scalar(select(Material.id).where(Material.filename == filename))


def english(client):
    client.get("/login?lang=en")


def test_sign_in_starts_a_background_sync(client, app):
    sign_in(client)
    assert app.config["STARTED_SYNCS"] == [(1, "login")]


def test_home_shows_courses_deadlines_grades_and_materials(client, app):
    english(client)
    synced(client, app)
    html = client.get("/").get_data(as_text=True)
    for text_ in ("Calculus 1", "Object Oriented Programming 1", "Homework 1", "22.00 / 25.00", "Lecture 3 slides",
                  "Last updated"):
        assert text_ in html, text_


def test_course_page_lists_weeks_files_links_and_the_assignment(client, app):
    english(client)
    synced(client, app)
    html = client.get("/course/2539").get_data(as_text=True)
    for text_ in ("Week 3", "Sep 19 – Sep 25", "lecture3.pdf", "reading1.pdf", "hw1.pdf",
                  YOUTUBE, "Submitted", "Grade: 22.00 / 25.00"):
        assert text_ in html, text_


def test_grades_page(client, app):
    synced(client, app)
    html = client.get("/grades").get_data(as_text=True)
    assert "Calculus 1" in html and "22.00 / 25.00" in html and "88%" in html


def test_another_students_course_and_files_stay_hidden(client, app):
    synced(client, app)
    other = app.test_client()
    uid = synced(other, app, "u2410002")
    with app.extensions["db_sessions"]() as db:  # the classmate only takes OOP
        db.execute(delete(Enrollment).where(Enrollment.user_id == uid, Enrollment.course_id == 2539))
        db.commit()
    assert other.get("/course/2539").status_code == 404
    assert other.get(f"/file/{material_id(app)}").status_code == 404
    assert "lecture3.pdf" not in other.get("/").get_data(as_text=True)
    assert client.get("/course/2539").status_code == 200


def test_files_are_streamed_with_the_students_session(client, app):
    synced(client, app)
    resp = client.get(f"/file/{material_id(app)}")
    assert resp.status_code == 200 and resp.data == b"%PDF-1.4 fake file"
    assert resp.mimetype == "application/pdf" and resp.headers["Content-Disposition"].startswith("inline")
    assert "no-store" in resp.headers["Cache-Control"] and "Content-Security-Policy" not in resp.headers


def test_html_from_eclass_is_downloaded_never_shown(client, app):
    synced(client, app)
    with app.extensions["db_sessions"]() as db:
        db.get(Material, material_id(app)).eclass_url = "https://eclass.inha.ac.kr/pluginfile.php/1/x/page.html"
        db.commit()
    resp = client.get(f"/file/{material_id(app)}")
    assert resp.mimetype == "application/octet-stream" and resp.headers["Content-Disposition"].startswith("attachment")


def test_files_only_come_from_eclass(client, app):
    synced(client, app)
    with app.extensions["db_sessions"]() as db:
        db.get(Material, material_id(app)).eclass_url = "https://evil.example/steal"
        db.commit()
    assert client.get(f"/file/{material_id(app)}").status_code == 404


def test_an_ended_eclass_session_asks_to_reconnect(client, app):
    uid = synced(client, app)
    with app.extensions["db_sessions"]() as db:
        db.execute(delete(EClassSession).where(EClassSession.user_id == uid))
        db.commit()
    resp = client.get(f"/file/{material_id(app)}")
    assert resp.status_code == 302 and resp.headers["Location"] == "/reconnect"
    token = csrf_token(client, "/")
    assert client.post("/sync", data={"csrf_token": token}).headers["Location"] == "/reconnect"
    resp = client.post("/reconnect", data={"password": FakeEClass.PASSWORD, "csrf_token": csrf_token(client, "/reconnect")})
    assert resp.status_code == 302 and resp.headers["Location"] == "/"
    with app.extensions["db_sessions"]() as db:
        assert db.get(EClassSession, uid) is not None
    assert app.config["STARTED_SYNCS"][-1] == (uid, "login")


def test_reconnect_with_a_wrong_password_is_refused(client, app):
    synced(client, app)
    resp = client.post("/reconnect", data={"password": "nope", "csrf_token": csrf_token(client, "/reconnect")})
    assert resp.status_code == 401


def test_refresh_button_and_status(client, app):
    english(client)
    uid = synced(client, app)
    resp = client.post("/sync", data={"csrf_token": csrf_token(client, "/")})
    assert resp.status_code == 302 and app.config["STARTED_SYNCS"][-1] == (uid, "button")
    status = client.get("/sync/status").get_json()
    assert status["state"] == "done" and "Last updated" in status["message"]
    assert client.post("/sync").status_code == 400  # CSRF


def test_links_from_eclass_are_only_http(client, app):
    synced(client, app)
    with app.extensions["db_sessions"]() as db:
        db.get(Activity, 702).url = "javascript:alert(document.cookie)"
        db.commit()
    assert "javascript:" not in client.get("/course/2539").get_data(as_text=True)
