"""Shared test fixtures: a throw-away database, a fake AI provider and no network access at all."""
import sqlite3
from pathlib import Path

import pytest
import requests

from eclass import db

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests never reach eClass, an AI provider or Telegram, whatever .env contains."""
    def blocked(*args, **kwargs):
        raise RuntimeError("network access is disabled in tests")
    monkeypatch.setattr(requests.Session, "request", blocked)
    monkeypatch.setattr(requests, "post", blocked)
    monkeypatch.setattr(requests, "get", blocked)


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    connection = db.connect(tmp_path / "eclass.db")
    yield connection
    connection.close()


def add_course(conn, course_id=2539, name="Calculus 1"):
    db.upsert_course(conn, {"id": course_id, "name": name, "code": None, "professor": None})


def add_activity(conn, activity_id, course_id=2539, kind="ubfile", name="Lecture", section=1):
    db.upsert_activity(conn, {"id": activity_id, "course_id": course_id, "section": section, "type": kind,
                              "name": name, "url": f"https://eclass.inha.ac.kr/mod/{kind}/view.php?id={activity_id}"})


class FakeProvider:
    """Answers the two chat calls (question rewrite, then answer) from canned values and records the prompts."""
    name, model = "fake", "fake-1"

    def __init__(self, answer=None, query="limit definition", error=None):
        self.answer = answer or {"answer": "Limit bu yaqinlashish [1].", "found": True, "cited": [1]}
        self.query, self.error, self.calls = query, error, []

    def complete_json(self, system, user, schema, max_tokens):
        self.calls.append({"system": system, "user": user, "schema": schema})
        if self.error:
            raise self.error
        if "standalone" in schema["properties"]:
            return {"standalone": user.rsplit("Latest message: ", 1)[-1], "query": self.query}
        return dict(self.answer)
