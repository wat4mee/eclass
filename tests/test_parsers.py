"""HTML parsing of eClass pages, from saved synthetic pages (no requests to the live site)."""
from bs4 import BeautifulSoup

from eclass import activities, courses, files
from tests.conftest import FIXTURES


def page(name):
    return BeautifulSoup((FIXTURES / name).read_text(), "html.parser")


class FakeClient:
    def __init__(self, pages):
        self.pages = pages

    def soup(self, path):
        return page(self.pages[path])


def test_list_courses_reads_course_cards_only():
    found = courses.list_courses(FakeClient({"/": "dashboard.html"}))
    assert found == [
        {"id": 2539, "name": "Calculus 1", "code": "MTH1001-05", "professor": "Test Professor"},
        {"id": 2562, "name": "Object Oriented Programming 1", "code": None, "professor": None},
    ]


def test_course_page_sections_are_deduplicated_and_ordered():
    sections = courses.parse_course_page(page("course.html"))
    assert [s["number"] for s in sections] == [0, 3, 4]
    assert sections[1]["name"] == "3Week [19 September - 25 September]"
    assert len(sections[1]["activities"]) == 1  # the repeated current week is not counted twice


def test_parse_activity_types_names_and_skips():
    sections = {s["number"]: s for s in courses.parse_course_page(page("course.html"))}
    rows = [activities.parse_activity(li, 2539, n) for n, s in sections.items() for li in s["activities"]]
    rows = [r for r in rows if r]
    assert [(r["id"], r["type"], r["name"]) for r in rows] == [
        (702, "url", "Lecture video 1"),          # the label (module-700) has no page: skipped
        (701, "ubfile", "Lecture 3 slides"),      # hidden " File" suffix removed
        (703, "assign", "Homework 1"),            # whitespace collapsed
        (704, "folder", "Readings"),
    ]                                             # an activity without a module id is ignored
    assert rows[0]["url"] == "https://eclass.inha.ac.kr/mod/url/view.php?id=702"
    assert all(r["course_id"] == 2539 for r in rows)


def test_parse_assign_fields_and_attachments():
    info, attachments = activities.parse_assign(page("assign.html"))
    assert info["due_date"] == "2026-09-25 15:00"
    assert info["submission_status"] == "Submitted for grading"
    assert info["grading_status"] == "Graded"
    assert info["grade"] == "22.00 / 25.00"
    assert info["intro"].startswith("Solve problems 1-10")
    assert attachments == [  # unique, and only inside the description
        "https://eclass.inha.ac.kr/pluginfile.php/123/mod_assign/intro/hw1.pdf",
        "https://eclass.inha.ac.kr/pluginfile.php/123/mod_assign/intro/data%20set.xlsx",
    ]


def test_pluginfile_links_fall_back_to_whole_page():
    links = activities.pluginfile_links(page("dashboard.html"))
    assert links == []
    links = activities.pluginfile_links(page("assign.html"), scope="#does-not-exist")
    assert links[0].endswith("banner.png") and len(links) == 3


class Headers(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class Resp:
    def __init__(self, url, headers=None):
        self.url, self.headers = url, Headers(headers or {})


def test_filename_from_content_disposition_and_url():
    utf8 = "attachment; filename*=UTF-8''Lecture%203%20%E2%80%94%20Limits.pdf"
    assert files.filename_from_response(Resp("https://x/pluginfile.php/1/a.pdf", {"Content-Disposition": utf8})) \
        == "Lecture 3 — Limits.pdf"
    assert files.filename_from_response(Resp("https://x/p", {"Content-Disposition": 'inline; filename="notes.pptx"'})) \
        == "notes.pptx"
    assert files.filename_from_response(Resp("https://x/pluginfile.php/1/mod_ubfile/content/0/week%201.pdf")) \
        == "week 1.pdf"


def test_safe_name_blocks_path_tricks():
    assert files.safe_name("../../etc/passwd") == "_.._etc_passwd"
    assert files.safe_name('a:b*c?"d<e>f|g') == "a_b_c__d_e_f_g"
    assert files.safe_name("  ") == "untitled"
    assert "/" not in files.safe_name("x/" * 100) and len(files.safe_name("y" * 500)) == 120
