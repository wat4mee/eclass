"""Milestone 4: study packs made by the scheduled job (fake AI), the study page and the "studied" mark."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select

from eclass.ai import DailyLimitReached
from web import packs
from web.models import Enrollment, Material, MaterialPage, PackNote, Progress, StudyPack
from tests.web.conftest import csrf_token
from tests.web.test_dashboard import material_id, synced

PACK = {"summary": "Hosila funksiyaning o'zgarish tezligini o'lchaydi.\nIkkinchi xat boshi.",
        "key_concepts": [{"term": "Derivative (hosila)", "explanation": "O'zgarish tezligi."}],
        "flashcards": [{"front": "Hosila nima?", "back": "O'zgarish tezligi."}],
        "quiz": [{"question": "sin x / x ning limiti?", "options": ["0", "1", "2", "yo'q"], "answer_index": 1,
                  "explanation": "Mashhur limit."},
                 {"question": "Buzuq savol", "options": ["a", "b"], "answer_index": 5, "explanation": ""}]}


class StudyAI:
    """Fake AI: notes for long files, then the pack; optionally the daily quota ends after `quota` calls."""
    name, model = "fake", "fake-study-1"

    def __init__(self, quota=None):
        self.quota, self.calls = quota, []

    def complete_json(self, system, user, schema, max_tokens):
        if self.quota is not None and len(self.calls) >= self.quota:
            raise DailyLimitReached("fake: daily quota used up")
        self.calls.append(user)
        if "notes" in schema["properties"]:
            return {"notes": f"notes of part {len(self.calls)}"}
        return dict(PACK)


@pytest.fixture
def student(client, app, monkeypatch):
    """A synced student; the fake lecture texts are short, so the minimum length for a pack is lowered."""
    monkeypatch.setattr(packs, "MIN_AI_CHARS", 10)
    return synced(client, app)


def generate(app, ai, limit=10):
    return packs.generate_pending(app.extensions["db_sessions"], ai, limit, sleep=lambda s: None)


def count(app, model):
    with app.extensions["db_sessions"]() as db:
        return db.scalar(select(func.count()).select_from(model))


def test_packs_are_made_for_readable_materials_and_shared(student, app):
    stats = generate(app, StudyAI())
    assert stats == {"generated": 3, "failed": 0, "stopped": None}  # the three PDFs; the spreadsheet has no text
    with app.extensions["db_sessions"]() as db:
        pack = db.scalar(select(StudyPack).where(StudyPack.material_id == material_id(app)))
        assert pack.language == "uz" and pack.model == "fake-study-1" and len(pack.quiz) == 1  # malformed dropped
    assert generate(app, StudyAI())["generated"] == 0  # nothing new: no AI calls


def test_a_changed_file_gets_a_new_pack(student, app):
    generate(app, StudyAI())
    with app.extensions["db_sessions"]() as db:
        db.get(Material, material_id(app)).sha256 = "0" * 64  # a new version of the lecture
        db.commit()
    assert generate(app, StudyAI())["generated"] == 1
    assert count(app, StudyPack) == 3


def test_the_daily_quota_stops_the_queue_and_long_files_resume(student, app):
    mid = material_id(app)
    with app.extensions["db_sessions"]() as db:  # a long lecture: 3 chunks of notes, then the pack
        db.add_all(MaterialPage(material_id=mid, page=p, text="x" * 9_000) for p in range(2, 5))
        lecture = db.get(Material, mid)
        lecture.n_chars, lecture.first_seen_at = 27_000, datetime.now(timezone.utc) + timedelta(days=1)  # newest
        db.commit()
    stats = generate(app, StudyAI(quota=2), limit=1)
    assert stats["stopped"] == "daily limit" and stats["generated"] == 0
    assert count(app, PackNote) == 2  # the notes made before the quota ended are kept
    ai = StudyAI()
    assert generate(app, ai, limit=1)["generated"] == 1
    assert len(ai.calls) == 2  # only the last chunk's notes and the pack itself


def test_the_study_page_shows_the_pack_to_enrolled_students_only(student, client, app):
    generate(app, StudyAI())
    mid = material_id(app)
    html = client.get(f"/study/{mid}").get_data(as_text=True)
    for text_ in ("Lecture 3 slides", "Hosila funksiyaning", "Derivative (hosila)", "Hosila nima?", "sin x / x"):
        assert text_ in html, text_
    assert f'href="/study/{mid}"' in client.get("/course/2539").get_data(as_text=True)
    assert f'href="/study/{mid}"' in client.get("/").get_data(as_text=True)
    other = app.test_client()
    uid = synced(other, app, "u2410002")
    with app.extensions["db_sessions"]() as db:  # the classmate only takes OOP
        db.execute(delete(Enrollment).where(Enrollment.user_id == uid, Enrollment.course_id == 2539))
        db.commit()
    assert other.get(f"/study/{mid}").status_code == 404


def test_no_pack_no_page(student, client, app):
    assert client.get(f"/study/{material_id(app)}").status_code == 404


def test_marking_a_material_studied(student, client, app):
    generate(app, StudyAI())
    mid = material_id(app)
    headers = {"X-CSRFToken": csrf_token(client, "/")}
    assert client.post(f"/api/studied/{mid}", json={"studied": True}, headers=headers).status_code == 200
    assert count(app, Progress) == 1
    assert "studied-btn on" in client.get(f"/study/{mid}").get_data(as_text=True)
    assert client.post(f"/api/studied/{mid}", json={"studied": False}, headers=headers).status_code == 200
    assert count(app, Progress) == 0
    assert client.post(f"/api/studied/{mid}", json={"studied": True}).status_code == 400  # CSRF
    assert client.post("/api/studied/999999", json={"studied": True}, headers=headers).status_code == 404
