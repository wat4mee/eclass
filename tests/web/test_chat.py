"""Milestone 3: Shahzod AI on the hosted site (fake AI, Postgres full-text search, the student's courses only)."""
import re

import pytest
from sqlalchemy import delete

from web.models import Enrollment
from web.views import ask
from tests.conftest import FakeProvider
from tests.web.test_dashboard import synced


@pytest.fixture
def chat(client, app, monkeypatch):
    """(post(question, **extra), provider, user id) for a synced student; the AI is fake."""
    uid = synced(client, app)
    provider = FakeProvider({"answer": "Hosila o'zgarish tezligini o'lchaydi [1].", "found": True, "cited": [1]},
                            query="derivative rate of change")
    monkeypatch.setattr(ask, "provider", lambda: provider)
    token = re.search(r'name="csrf-token" content="([^"]+)"', client.get("/ask").get_data(as_text=True)).group(1)

    def post(question="Hosila nima?", headers=None, **extra):
        return client.post("/api/ask", json={"question": question, **extra},
                           headers={"X-CSRFToken": token} if headers is None else headers)
    return post, provider, uid


def test_answers_cite_the_students_own_materials(chat):
    post, provider, _ = chat
    data = post().get_json()
    assert data["found"] is True and data["answer"] == "Hosila o'zgarish tezligini o'lchaydi [1]."
    [source] = data["sources"]
    assert source["filename"] == "lecture3.pdf" and source["page"] == 1
    assert "Derivatives measure the rate of change" in source["text"]
    assert "Course:" not in provider.calls[0]["user"]  # all courses


def test_the_chat_needs_its_csrf_token(chat):
    post, _, _ = chat
    assert post(headers={}).status_code == 400


def test_unrelated_questions_get_no_sources_and_no_ai_answer(chat):
    post, provider, _ = chat
    provider.query = "pointer memory address"
    data = post("Pointer nima?").get_json()
    assert data["found"] is False and data["sources"] == []
    assert len(provider.calls) == 1  # only the question rewrite


def test_a_course_filter_names_the_course_and_must_be_the_students(chat, app):
    post, provider, uid = chat
    assert post(course_id=2539).status_code == 200 and provider.calls[0]["user"].startswith("Course: Calculus 1")
    assert post(course_id=9999).status_code == 404
    with app.extensions["db_sessions"]() as db:
        db.execute(delete(Enrollment).where(Enrollment.user_id == uid, Enrollment.course_id == 2539))
        db.commit()
    assert post(course_id=2539).status_code == 404
    assert post().get_json()["sources"] == []  # the material is no longer the student's


def test_daily_question_limit(chat, app):
    post, _, _ = chat
    app.config["AI_DAILY_LIMIT"] = 2
    assert [post().status_code for _ in range(3)] == [200, 200, 429]


def test_bad_requests(chat):
    post, _, _ = chat
    assert post("").status_code == 400 and post("x" * 1001).status_code == 400
