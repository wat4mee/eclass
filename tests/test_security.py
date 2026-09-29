"""Security checks of the dashboard: local-only requests, CSRF, headers, path traversal, SQL/FTS injection, XSS."""
import pytest

import app as web
from eclass import db
from tests.conftest import add_activity, add_course
from tests.test_ask import ORIGIN, client  # noqa: F401  (fixture)

XSS = "<script>alert(1)</script>"


def test_debug_is_off_and_host_is_local():
    assert web.app.debug is False
    assert web.LOCAL_HOSTS == {"127.0.0.1", "localhost"}


def test_security_headers(client):  # noqa: F811
    for path in ("/", "/api/search?q=limit", "/does-not-exist"):
        headers = client.get(path).headers
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Referrer-Policy"] == "same-origin"


@pytest.mark.parametrize("path", ["/api/ask", "/api/sync", "/api/studied/1", "/api/translate/1", "/api/chapter/1/0"])
def test_state_changing_endpoints_reject_other_sites(client, path):  # noqa: F811
    assert client.post(path, json={}).status_code == 403                                           # no Origin/Referer
    assert client.post(path, json={}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert client.post(path, json={}, headers={"Referer": "http://localhost.evil.example/x"}).status_code == 403
    assert client.post(path, data="x", headers=ORIGIN | {"Content-Type": "text/plain"}).status_code in (404, 415)


def test_foreign_host_header_is_rejected(client):  # noqa: F811  (DNS rebinding)
    assert client.get("/", headers={"Host": "attacker.example"}).status_code == 400
    assert client.get("/", headers={"Host": "127.0.0.1:5050"}).status_code == 200


@pytest.fixture
def files_dir(tmp_path, monkeypatch):
    root = (tmp_path / "files").resolve()
    (root / "Calculus 1").mkdir(parents=True)
    (root / "Calculus 1" / "notes.pdf").write_bytes(b"%PDF-1.4 test")
    monkeypatch.setattr(web, "FILES_DIR", root)
    conn = db.connect(web.DB_PATH)
    add_activity(conn, 900, name="Video")
    for fid, path, source in ((10, str(root / "Calculus 1" / "notes.pdf"), None),
                              (11, str(root / ".." / ".." / "etc" / "passwd"), None),
                              (12, "/etc/hosts", None),
                              (13, "youtube:abc123DEF45", "javascript:alert(1)"),
                              (14, "youtube:abc123DEF45", "https://www.youtube.com/watch?v=abc123DEF45")):
        conn.execute("INSERT INTO files (id, activity_id, filename, path, sha256, size, downloaded_at, source_url) "
                     "VALUES (?, 900, ?, ?, 'x', 1, 'now', ?)", (fid, f"f{fid}", path, source))
    conn.commit()
    conn.close()
    return root


def test_files_are_served_by_id_and_only_from_the_files_folder(client, files_dir):  # noqa: F811
    assert client.get("/file/10").data == b"%PDF-1.4 test"
    assert client.get("/file/11").status_code == 404   # ../ in a stored path
    assert client.get("/file/12").status_code == 404   # absolute path outside data/files
    assert client.get("/file/abc").status_code == 404  # ids only, never names
    assert client.get("/file/..%2F..%2Fetc%2Fpasswd").status_code == 404


def test_video_redirect_only_to_web_links(client, files_dir):  # noqa: F811
    assert client.get("/file/13").headers["Location"] == "https://youtu.be/abc123DEF45"
    assert client.get("/file/14").headers["Location"].startswith("https://www.youtube.com/")


@pytest.mark.parametrize("q", ["' OR 1=1 --", '" OR "', "limit\") OR (\"", "NEAR(a b)", "*", "%", "; DROP TABLE files;"])
def test_search_input_is_never_sql(client, q):  # noqa: F811
    resp = client.get("/api/search", query_string={"q": q})
    assert resp.status_code == 200 and isinstance(resp.get_json()["results"], list)
    conn = db.connect(web.DB_PATH)
    assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 5
    conn.close()


def test_names_from_eclass_are_escaped(client):  # noqa: F811
    conn = db.connect(web.DB_PATH)
    add_course(conn, 3000, f"Hacked {XSS}")
    conn.commit()
    conn.close()
    assert XSS not in client.get("/").get_data(as_text=True)
    results = client.get("/api/search", query_string={"q": "hacked"}).get_json()["results"]
    assert results and XSS not in results[0]["title_html"] and "&lt;script&gt;" in results[0]["title_html"]
