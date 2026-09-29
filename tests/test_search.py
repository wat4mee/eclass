"""Course Q&A retrieval: indexing, hybrid search, course filter, at most 2 chunks per page (fake embedder)."""
import numpy as np
import pytest

from eclass import db, rag
from tests.conftest import add_activity, add_course


class FakeEmbedder:
    """Bag-of-words vectors over a tiny vocabulary: enough to rank passages by topic without a model."""
    VOCAB = ["limit", "derivative", "integral", "class", "pointer", "object"]

    def _vec(self, text):
        v = np.array([text.lower().count(w) for w in self.VOCAB] + [0.05], dtype=np.float32)
        return v / np.linalg.norm(v)

    def embed(self, texts, batch_size=16):
        return [self._vec(t) for t in texts]

    def query_embed(self, texts):
        return [self._vec(t) for t in texts]


@pytest.fixture
def indexed(conn, monkeypatch):
    monkeypatch.setattr(rag, "_embedder", lambda: FakeEmbedder())
    add_course(conn, 2539, "Calculus 1")
    add_course(conn, 2562, "Object Oriented Programming 1")
    add_activity(conn, 701, 2539, name="Limits")
    add_activity(conn, 801, 2562, name="Classes")
    long_limit_page = " ".join(["The limit of f(x) as x approaches a is L."] * 120)  # several chunks on one page
    for file_id, activity, pages in (
            (1, 701, [long_limit_page, "The derivative is the limit of a difference quotient.", "An integral adds areas."]),
            (2, 801, ["A class describes an object.", "A pointer stores the address of an object."])):
        conn.execute("INSERT INTO files (id, activity_id, filename, path, sha256, size, downloaded_at) "
                     "VALUES (?, ?, ?, ?, ?, 1, 'now')", (file_id, activity, f"f{file_id}.pdf", f"/x/{file_id}", f"h{file_id}"))
        db.save_extraction(conn, file_id, f"h{file_id}", "pdf", pages)
    stats = rag.index_pending(conn, log=lambda *_: None)
    assert stats["files"] == 2 and stats["chunks"] > 5
    return conn


def test_search_ranks_by_topic_with_full_rows(indexed):
    results = rag.search(indexed, "limit")
    assert results[0]["file_id"] == 1 and results[0]["course"] == "Calculus 1"
    assert {"id", "file_id", "page", "text", "filename", "activity", "course_id", "course", "score", "sim"} <= results[0].keys()
    assert results[0]["sim"] > 0.9


def test_at_most_two_chunks_per_page(indexed):
    pages = [(r["file_id"], r["page"]) for r in rag.search(indexed, "limit")]
    assert max(pages.count(p) for p in set(pages)) <= 2


def test_course_filter(indexed):
    results = rag.search(indexed, "limit", course_id=2562)
    assert results and all(r["course_id"] == 2562 for r in results)
    assert rag.search(indexed, "pointer object")[0]["file_id"] == 2


def test_indexing_is_done_once(indexed):
    assert rag.index_pending(indexed, log=lambda *_: None) == {"files": 0, "chunks": 0}
