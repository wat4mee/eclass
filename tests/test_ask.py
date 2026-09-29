"""/api/ask end to end with a fake AI: source filtering, at most 3 sources, chat memory, request guards."""
import pytest

import app as web
from eclass import ai, db, i18n, rag
from tests.conftest import FakeProvider, add_activity, add_course

ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "eclass.db"
    conn = db.connect(path)
    add_course(conn)
    for i in range(1, 6):
        add_activity(conn, 700 + i, name=f"Lecture {i}")
        conn.execute("INSERT INTO files (id, activity_id, filename, path, sha256, size, downloaded_at) "
                     "VALUES (?, ?, ?, ?, 'x', 1, 'now')", (i, 700 + i, f"lecture{i}.pdf", str(tmp_path / f"{i}.pdf")))
    conn.commit()
    conn.close()
    monkeypatch.setattr(web, "DB_PATH", path)
    monkeypatch.setattr(web, "DATA_DIR", tmp_path)
    monkeypatch.setattr(web.time, "sleep", lambda _s: None)  # the one retry after an AI error waits 2 s
    web.app.config["TESTING"] = True
    return web.app.test_client()


def passage(n, file_id=None, page=1, sim=0.8):
    file_id = file_id or n
    return {"id": n, "file_id": file_id, "page": page, "text": f"passage {n}", "filename": f"lecture{file_id}.pdf",
            "activity": f"Lecture {file_id}", "course_id": 2539, "course": "Calculus 1", "score": 1.0, "sim": sim}


@pytest.fixture
def setup(monkeypatch):
    def use(provider, passages):
        monkeypatch.setattr(web, "get_provider", lambda **_settings: provider)
        monkeypatch.setattr(rag, "search", lambda conn, query, course_id=None, k=rag.TOP_K: list(passages))
        return provider
    return use


def ask(client, question="Limit nima?", **extra):
    return client.post("/api/ask", json={"question": question, **extra}, headers=ORIGIN)


def test_at_most_three_sources_and_citations_renumbered(client, setup):
    setup(FakeProvider({"answer": "a [1], b [2], c [3], d [4], e [5].", "found": True, "cited": [1, 2, 3, 4, 5]}),
          [passage(n) for n in range(1, 6)])
    data = ask(client).get_json()
    assert data["found"] is True
    assert [s["n"] for s in data["sources"]] == [1, 2, 3]
    assert "[4]" not in data["answer"] and "[5]" not in data["answer"]
    assert data["answer"].startswith("a [1], b [2], c [3]")


def test_nearby_pages_of_one_file_are_one_source(client, setup):
    setup(FakeProvider({"answer": "x [1] y [2] z [3].", "found": True, "cited": [1, 2, 3]}),
          [passage(1, file_id=1, page=3), passage(2, file_id=1, page=4), passage(3, file_id=2, page=9)])
    data = ask(client).get_json()
    assert [(s["file_id"], s["pages"]) for s in data["sources"]] == [(1, [3, 4]), (2, [9])]
    assert data["answer"] == "x [1] y [1] z [2]."


def test_unrelated_passages_give_no_sources_and_no_ai_answer(client, setup):
    provider = setup(FakeProvider(), [passage(1, sim=0.5), passage(2, sim=0.4)])
    data = ask(client).get_json()
    assert data == data | {"found": False, "sources": [], "answer": i18n.t("uz", "ask.not_found")}
    assert len(provider.calls) == 1  # only the question rewrite, no answer call


def test_model_not_found_shows_no_sources_or_markers(client, setup):
    setup(FakeProvider({"answer": "Materiallarda bu yo'q [2].", "found": False, "cited": []}), [passage(1), passage(2)])
    data = ask(client).get_json()
    assert data["found"] is False and data["sources"] == []
    assert data["answer"] == "Materiallarda bu yo'q."


def test_json_field_names_do_not_leak(client, setup):
    setup(FakeProvider({"answer": "Limit bu yaqinlashish [1], va mos ravishda found=true.", "found": True, "cited": [1]}),
          [passage(1)])
    answer = ask(client).get_json()["answer"]
    assert "found" not in answer and answer == "Limit bu yaqinlashish [1]."


def test_chat_memory_keeps_the_last_turns(client, setup):
    provider = setup(FakeProvider(), [passage(1)])
    history = [{"q": f"savol {i}", "a": f"javob {i}"} for i in range(6)]
    assert ask(client, "Unga misol ber", history=history).status_code == 200
    rewrite, answer = provider.calls[0]["user"], provider.calls[1]["user"]
    assert "Student: savol 5" in rewrite and "Assistant: javob 5" in rewrite
    assert "savol 1" not in rewrite and "savol 2" in rewrite  # only the last rag.HISTORY_TURNS (4) turns
    assert rewrite.endswith("Latest message: Unga misol ber")
    assert "Conversation so far:" in answer


def test_ai_errors_become_friendly_messages(client, setup):
    setup(FakeProvider(error=ai.DailyLimitReached("groq: per day")), [passage(1)])
    resp = ask(client)
    assert resp.status_code == 429 and resp.get_json()["error"] == i18n.t("uz", "err.ai_quota")
    setup(FakeProvider(error=ai.AIError("gemini 500: internal")), [passage(1)])
    resp = ask(client)
    assert resp.status_code == 502 and resp.get_json()["error"] == i18n.t("uz", "err.ai")
    assert "internal" not in resp.get_data(as_text=True)  # provider details stay in the server log


def test_request_guards(client, setup):
    setup(FakeProvider(), [passage(1)])
    assert client.post("/api/ask", json={"question": "x"}).status_code == 403                      # no Origin
    assert client.post("/api/ask", json={"question": "x"},
                       headers={"Origin": "https://evil.example"}).status_code == 403              # cross-site
    assert client.post("/api/ask", data={"question": "x"}, headers=ORIGIN).status_code == 415      # not JSON
    assert client.post("/api/ask", json={"question": "x"}, headers=ORIGIN | {"Host": "evil.example"}).status_code == 400
    assert ask(client, "x" * 1001).status_code == 400
    assert ask(client, "   ").status_code == 400
