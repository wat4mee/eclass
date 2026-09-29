"""Failure handling: typed eClass errors, sync history, AI time limits and fallback, message language."""
import time
from collections import Counter

import pytest
import requests

import app as web
import sync
from eclass import ai, auth, db, i18n, notify
from tests.conftest import FakeProvider
from tests.test_ask import ORIGIN, client, passage, setup  # noqa: F401  (fixtures)


# ---------------------------------------------------------------- eClass client errors

class Resp:
    def __init__(self, status, url="https://eclass.inha.ac.kr/course/view.php?id=1"):
        self.status_code, self.url, self.is_redirect, self.headers, self.text = status, url, False, {}, ""

    def close(self):
        pass


@pytest.fixture
def eclass_client(monkeypatch):
    monkeypatch.setenv("ECLASS_USER", "student")
    monkeypatch.setenv("ECLASS_PASS", "s3cret-pass")
    monkeypatch.setattr(auth, "MIN_INTERVAL", 0)
    return auth.EClassClient()


@pytest.mark.parametrize("failure, error, code", [
    (requests.Timeout("read timed out"), auth.EClassTimeout, "timeout"),
    (requests.ConnectionError("Name or service not known"), auth.NetworkError, "network"),
    (Resp(503), auth.ServerError, "server"),
    (Resp(404), auth.PageError, "page"),
])
def test_eclass_failures_have_a_type_and_code(eclass_client, failure, error, code):
    def respond(*args, **kwargs):
        if isinstance(failure, Exception):
            raise failure
        return failure
    eclass_client.session.request = respond
    with pytest.raises(error) as caught:
        eclass_client.get("/course/view.php?id=1")
    assert caught.value.code == code
    assert "s3cret-pass" not in str(caught.value) and "/course/view.php" in str(caught.value)


def test_missing_credentials_is_a_config_error(monkeypatch):
    monkeypatch.setenv("ECLASS_USER", "")
    with pytest.raises(auth.ConfigError):
        auth.EClassClient()


def test_session_that_cannot_be_renewed(eclass_client, monkeypatch):
    eclass_client.session.request = lambda *a, **k: Resp(200, "https://eclass.inha.ac.kr/login.php")
    monkeypatch.setattr(eclass_client, "login", lambda: True)
    with pytest.raises(auth.SessionExpired) as caught:
        eclass_client.get("/my/")
    assert caught.value.code == "session" and isinstance(caught.value, auth.LoginError)


# ---------------------------------------------------------------- sync history

@pytest.fixture
def sync_env(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sync, "RUN_LOCK", tmp_path / ".run.lock")
    monkeypatch.setattr(sync, "NEW_ITEMS", [])
    monkeypatch.setenv("ECLASS_PASS", "s3cret-pass")
    return tmp_path


def run_sync(tmp_path):
    return sync.main(["--all", "--db", str(tmp_path / "eclass.db"), "--trigger", "terminal"])


def test_failed_sync_is_recorded_without_the_password(sync_env, monkeypatch):
    def fail(args, conn):
        raise auth.LoginError("login failed for student / s3cret-pass")
    monkeypatch.setattr(sync, "run", fail)
    assert run_sync(sync_env) == 2
    row = db.sync_runs(db.connect(sync_env / "eclass.db"))[0]
    assert (row["state"], row["code"], row["started_by"]) == ("error", "login", "terminal")
    assert "s3cret-pass" not in row["detail"] and "***" in row["detail"]
    assert row["finished_at"]


def test_successful_and_crashed_syncs_are_recorded(sync_env, monkeypatch):
    def ok(args, conn):
        sync.remember("material", "Calculus 1", "Lecture 4")
        return 1, Counter(files_new=1, errors=2)
    monkeypatch.setattr(sync, "run", ok)
    run_sync(sync_env)
    monkeypatch.setattr(sync, "run", lambda args, conn: 1 / 0)
    assert run_sync(sync_env) == 4
    crashed, done = db.sync_runs(db.connect(sync_env / "eclass.db"))
    assert (done["state"], done["new_items"], done["errors"]) == ("done", 1, 2)
    assert (crashed["state"], crashed["code"], crashed["detail"]) == ("error", "other", "ZeroDivisionError: division by zero")


@pytest.fixture
def offline_run(conn, monkeypatch):
    """sync.run with the eClass client and the post-sync steps replaced; returns (run, synced course ids)."""
    class Client:
        request_count = 0

        def login(self):
            return True
    monkeypatch.setattr(sync, "EClassClient", Client)
    monkeypatch.setattr(sync, "list_courses", lambda client: [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}])
    for step in ("videos.process", "extract.extract_pending"):
        module, name = step.split(".")
        monkeypatch.setattr(getattr(sync, module), name, lambda *a, **k: {})
    monkeypatch.setattr(sync.rag, "index_pending", lambda *a, **k: {})
    synced = []
    args = sync.parse_args(["--all", "--no-ai", "--no-notify", "--trigger", "terminal"])
    return (lambda: sync.run(args, conn)), synced


def test_one_failing_course_does_not_stop_the_others(offline_run, monkeypatch):
    run, synced = offline_run

    def sync_course(client, conn, course, *rest):
        if course["id"] == 1:
            raise auth.EClassTimeout("no answer within 60 s: /course/view.php")
        synced.append(course["id"])
    monkeypatch.setattr(sync, "sync_course", sync_course)
    code, stats = run()
    assert synced == [2] and stats["errors"] == 1 and code == 1


def test_every_course_failing_reports_the_reason(offline_run, monkeypatch):
    run, _ = offline_run
    monkeypatch.setattr(sync, "sync_course", lambda *a: (_ for _ in ()).throw(auth.ServerError("HTTP 503: /course/view.php")))
    with pytest.raises(auth.ServerError):
        run()


def test_home_page_shows_the_sync_history(client):  # noqa: F811
    conn = db.connect(web.DB_PATH)
    db.finish_sync_run(conn, db.start_sync_run(conn, "schedule"), "done", new_items=3)
    db.finish_sync_run(conn, db.start_sync_run(conn, "dashboard"), "error", code="timeout", detail="no answer within 60 s")
    db.start_sync_run(conn, "terminal")  # never finished and no run is active: shown as stopped
    conn.close()
    html = client.get("/").get_data(as_text=True)
    for text in (i18n.t("uz", "sync.history.title"), i18n.t("uz", "sync.hist.new", n=3), i18n.t("uz", "sync.err.timeout"),
                 i18n.t("uz", "sync.err.stopped"), i18n.t("uz", "sync.by.dashboard"), 'title="no answer within 60 s"'):
        assert text.replace("'", "&#39;") in html
    rows = [html.index(f'class="sh sh-{state}"') for state in ("stopped", "error", "done")]
    assert rows == sorted(rows)  # newest first


# ---------------------------------------------------------------- AI time limits and fallback

class Slow:
    name, model, deadline, patient = "slow", "slow-1", None, True

    def complete_json(self, *args):
        raise ai.AITimeout("slow-1: ReadTimeout after 30 s")


def test_chain_skips_a_slow_model():
    fast = FakeProvider()
    chain = ai.ChainProvider([Slow(), fast])
    assert chain.complete_json("s", "Latest message: x", {"properties": {"standalone": {}}}, 10)["query"]
    assert chain.model == "fake-1"


def test_chain_stops_when_the_time_budget_is_spent():
    chain = ai.ChainProvider([FakeProvider()], deadline=time.monotonic() + 1)
    with pytest.raises(ai.AITimeout):
        chain.complete_json("s", "u", {"properties": {}}, 10)


def test_http_timeout_is_capped_by_the_deadline(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    seen = {}

    def post(url, json, timeout, headers):
        seen["timeout"] = timeout
        raise requests.Timeout()
    monkeypatch.setattr(ai.requests, "post", post)
    provider = ai.GeminiProvider(timeout=30)
    provider.deadline = time.monotonic() + 12
    with pytest.raises(ai.AITimeout):
        provider.complete_json("s", "u", {"properties": {}}, 10)
    assert 9 < seen["timeout"] <= 12


def test_fallback_models_are_tried_last(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("AI_PROVIDER", "gemini:gemini-a")
    monkeypatch.setenv("AI_FALLBACK", "gemini:gemini-b, gemini:gemini-a")
    monkeypatch.setattr(ai, "load_dotenv", lambda: None)
    chain = ai.get_provider(timeout=7)
    assert [(p.model, p.timeout) for p in chain.providers] == [("gemini-a", 7), ("gemini-b", 7)]


def test_slow_ai_in_chat_gives_a_timeout_message(client, setup):  # noqa: F811
    setup(FakeProvider(error=ai.AITimeout("gemini: ReadTimeout")), [passage(1)])
    resp = client.post("/api/ask", json={"question": "Limit nima?"}, headers=ORIGIN)
    assert resp.status_code == 504 and resp.get_json()["error"] == i18n.t("uz", "err.ai_timeout")


# ---------------------------------------------------------------- texts

def test_every_text_has_all_languages():
    missing = [k for k, v in i18n.S.items() if not {"uz", "en", "ru"} <= set(v)]
    assert not missing


def test_telegram_language_setting(monkeypatch):
    events = [{"key": "k", "kind": "grade", "course": "Calculus 1", "text": "HW1: <b>9 / 10</b>"}]
    assert notify.build_messages(events)[0][0].startswith("🎓 <b>Yangi baholar</b>")
    monkeypatch.setattr(notify, "NOTIFY_LANGUAGE", "en")
    assert notify.build_messages(events)[0][0].startswith("🎓 <b>New grades</b>")
