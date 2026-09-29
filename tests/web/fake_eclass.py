"""A fake eClass site for sync tests, built from the saved pages in tests/fixtures (no network, no credentials).

Dashboard: courses 2539 (Calculus 1) and 2562 (OOP 1). Course 2539 has a ubfile (701 -> lecture3.pdf), a video
link (702 -> YouTube), an assignment (703, graded 22/25, with hw1.pdf and "data set.xlsx") and a folder
(704 -> reading1.pdf). Course 2562 is empty.
"""
from bs4 import BeautifulSoup

from eclass.auth import PageError, SessionExpired
from tests.conftest import FIXTURES

BASE = "https://eclass.inha.ac.kr"
YOUTUBE = "https://www.youtube.com/watch?v=abc123DEF45"


def make_pdf(text: str) -> bytes:
    import pymupdf
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72, 72), text)
        return doc.tobytes()


LECTURE = make_pdf("Derivatives measure the rate of change of a function.")
HOMEWORK = make_pdf("Homework: compute the limit of sin x over x.")
READING = make_pdf("Reading: integrals add up areas under a curve.")


class FakeResponse:
    def __init__(self, url, content=b"", content_type="text/html", redirect_to=None):
        self.url, self.content, self.status_code = url, content, 302 if redirect_to else 200
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(content))}
        if redirect_to:
            self.headers["Location"] = redirect_to
        self.is_redirect, self.read, self.closed = bool(redirect_to), False, False

    @property
    def text(self):
        return self.content.decode()

    def iter_content(self, size):
        self.read = True
        for i in range(0, len(self.content), size):
            yield self.content[i:i + size]

    def close(self):
        self.closed = True


class FakeSite:
    """Stands in for eclass.auth.EClassClient during a sync."""
    base_url = BASE

    def __init__(self, courses=(2539, 2562), broken=(), expired=False, fail=None):
        self.courses, self.broken, self.expired, self.fail = set(courses), set(broken), expired, fail
        self.responses: list[FakeResponse] = []

    def _page(self, path: str) -> str:
        if self.expired:
            raise SessionExpired("eClass session expired")
        if self.fail:
            raise self.fail
        path = path.replace(BASE, "")
        if path == "/":
            soup = BeautifulSoup((FIXTURES / "dashboard.html").read_text(), "html.parser")
            for a in soup.select('a[href*="course/view.php?id="]'):  # hide courses the student no longer has
                if not any(f"id={cid}" in a["href"] for cid in self.courses):
                    a.decompose()
            return str(soup)
        if path.startswith("/course/view.php?id="):
            cid = int(path.split("=")[1])
            if cid in self.broken:
                raise PageError(f"HTTP 500: {path}")
            return (FIXTURES / "course.html").read_text() if cid == 2539 else "<html><body></body></html>"
        if path == "/mod/assign/view.php?id=703":
            return (FIXTURES / "assign.html").read_text()
        if path == "/mod/folder/view.php?id=704":
            return ('<div id="region-main"><a href="https://eclass.inha.ac.kr/pluginfile.php/5/mod_folder/content/0/'
                    'reading1.pdf">reading1.pdf</a></div>')
        raise PageError(f"HTTP 404: {path}")

    def soup(self, path):
        return BeautifulSoup(self._page(path), "html.parser")

    def get(self, path, stream=False, allow_redirects=True):
        if self.expired:
            raise SessionExpired("eClass session expired")
        path = path.replace(BASE, "")
        if path == "/mod/url/view.php?id=702":
            resp = FakeResponse(BASE + path, redirect_to=YOUTUBE)
        elif path == "/mod/ubfile/view.php?id=701":
            resp = FakeResponse(BASE + "/pluginfile.php/1/mod_ubfile/content/0/lecture3.pdf", LECTURE, "application/pdf")
        elif path.endswith("/hw1.pdf"):
            resp = FakeResponse(BASE + path, HOMEWORK, "application/pdf")
        elif path.endswith("/data%20set.xlsx"):
            resp = FakeResponse(BASE + path, b"PK\x03\x04 fake spreadsheet", "application/vnd.ms-excel")
        elif path.endswith("/reading1.pdf"):
            resp = FakeResponse(BASE + path, READING, "application/pdf")
        else:
            resp = FakeResponse(BASE + path, self._page(path).encode())
        self.responses.append(resp)
        return resp

    def downloaded(self) -> list[str]:
        """URLs whose body was actually read."""
        return [r.url for r in self.responses if r.read]
