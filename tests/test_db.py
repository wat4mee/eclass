"""Database upserts and sha256-based de-duplication of downloaded files."""
import hashlib

import pytest

from eclass import db, files
from tests.conftest import add_activity, add_course


def test_upsert_course_reports_new_only_once(conn):
    course = {"id": 2539, "name": "Calculus 1", "code": "MTH1001", "professor": None}
    assert db.upsert_course(conn, course) is True
    assert db.upsert_course(conn, course | {"name": "Calculus I"}) is False
    rows = conn.execute("SELECT name FROM courses").fetchall()
    assert [r["name"] for r in rows] == ["Calculus I"]


def test_upsert_activity_and_section(conn):
    add_course(conn)
    assert db.upsert_section(conn, 2539, 3, "3Week") is True
    assert db.upsert_section(conn, 2539, 3, "3Week [19 - 25]") is False
    act = {"id": 701, "course_id": 2539, "section": 3, "type": "ubfile", "name": "Slides", "url": "u"}
    assert db.upsert_activity(conn, act) is True
    assert db.upsert_activity(conn, act | {"name": "Slides v2"}) is False
    assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 1


def test_upsert_assignment_returns_previous_row(conn):
    add_course(conn)
    add_activity(conn, 703, kind="assign")
    info = {"due_date": "2026-09-25 15:00", "submission_status": "No attempt", "grading_status": None,
            "grade": None, "intro": "x"}
    assert db.upsert_assignment(conn, 703, info) is None
    previous = db.upsert_assignment(conn, 703, info | {"grade": "22.00 / 25.00"})
    assert previous["grade"] is None
    assert conn.execute("SELECT grade FROM assignments").fetchone()[0] == "22.00 / 25.00"


class FakeResponse:
    def __init__(self, body, name="notes.pdf"):
        self.body = body
        self.url = f"https://eclass.inha.ac.kr/pluginfile.php/1/mod_ubfile/content/0/{name}"
        self.headers = {}

    def iter_content(self, _size):
        yield self.body

    def close(self):
        pass


@pytest.fixture
def course_with_file(conn):
    add_course(conn)
    add_activity(conn, 701)
    return conn


def test_save_response_dedupes_by_sha256(course_with_file, tmp_path):
    conn = course_with_file
    assert files.save_response(conn, 701, FakeResponse(b"v1"), tmp_path) == "new"
    assert files.save_response(conn, 701, FakeResponse(b"v1"), tmp_path) == "unchanged"
    assert files.save_response(conn, 701, FakeResponse(b"v2"), tmp_path) == "updated"
    rows = db.get_files(conn, 701)
    assert len(rows) == 1
    assert rows[0]["sha256"] == hashlib.sha256(b"v2").hexdigest() and rows[0]["size"] == 2
    assert (tmp_path / "notes.pdf").read_bytes() == b"v2"
    assert not list(tmp_path.glob("*.part"))  # no temporary files left behind


def test_same_filename_from_another_activity_is_not_overwritten(course_with_file, tmp_path):
    conn = course_with_file
    add_activity(conn, 702)
    files.save_response(conn, 701, FakeResponse(b"first"), tmp_path)
    files.save_response(conn, 702, FakeResponse(b"second"), tmp_path)
    assert (tmp_path / "notes.pdf").read_bytes() == b"first"
    assert (tmp_path / "notes [702].pdf").read_bytes() == b"second"


class NoRequests:
    def get(self, *args, **kwargs):
        raise AssertionError("an intact file must not be downloaded again")


def test_download_links_skips_intact_files(course_with_file, tmp_path):
    conn = course_with_file
    files.save_response(conn, 701, FakeResponse(b"v1"), tmp_path)
    url = "https://eclass.inha.ac.kr/pluginfile.php/1/mod_ubfile/content/0/notes.pdf"
    assert files.download_links(NoRequests(), conn, 701, [url], tmp_path) == ["skipped"]


def test_pack_columns_and_save_study(course_with_file):
    conn = course_with_file
    conn.execute("INSERT INTO files (activity_id, filename, path, sha256, size, downloaded_at) "
                 "VALUES (701, 'a.pdf', '/tmp/a.pdf', 'abc', 1, 'now')")
    pack = {"summary": "S", "key_concepts": [{"term": "limit", "explanation": "$\\lim$"}],
            "flashcards": [], "quiz": []}
    db.save_study(conn, 1, "abc", "fake", "m", "uz", pack)
    row = conn.execute("SELECT summary, concepts FROM study").fetchone()
    assert row["summary"] == "S" and '"$\\\\lim$"' in row["concepts"]
