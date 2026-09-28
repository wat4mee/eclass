"""Course Q&A: hybrid retrieval (FTS5 keywords + local embeddings) and cited answers.

Materials are English while questions are usually Uzbek, so each question is first
rewritten into an English search query by the LLM; retrieval then runs locally and
the LLM answers only from the retrieved passages, citing file and page.
"""
import os
import re
from pathlib import Path

import numpy as np

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models"
CHUNK_CHARS = 1200
OVERLAP = 200
TOP_K = 8
EMBED_THREADS = int(os.getenv("EMBED_THREADS", "2"))  # keep the Mac responsive; 0 = all cores
PAGE_BATCH = 40  # pages embedded and committed per step, so textbooks resume after an interruption
_CANDIDATES = 40
_RRF_K = 60

_model = None


def _embedder():
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        _model = TextEmbedding(EMBED_MODEL, cache_dir=str(MODEL_DIR), threads=EMBED_THREADS or None)
    return _model


def split_page(text, size=CHUNK_CHARS, overlap=OVERLAP):
    """Split one page into overlapping chunks, preferring paragraph/sentence boundaries."""
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = max(text.rfind("\n", start + size // 2, end), text.rfind(". ", start + size // 2, end))
            if cut > start:
                end = cut + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = end - overlap
    return [c for c in chunks if c]


# ---------------------------------------------------------------- indexing

def _backfill_state(conn):
    """Files indexed before index_state existed were written in one transaction, so they are complete."""
    conn.execute(
        """INSERT OR IGNORE INTO index_state (file_id, sha256, done_page, complete)
           SELECT c.file_id, c.sha256, MAX(c.page), 1 FROM chunks c
           JOIN files f ON f.id = c.file_id AND f.sha256 = c.sha256 GROUP BY c.file_id""")
    conn.commit()


def pending_files(conn):
    """Extracted files not fully indexed for their current version, smallest first."""
    _backfill_state(conn)
    return conn.execute(
        """SELECT f.id, f.filename, f.sha256, e.n_pages FROM files f
           JOIN extractions e ON e.file_id = f.id AND e.sha256 = f.sha256
           LEFT JOIN index_state s ON s.file_id = f.id AND s.sha256 = f.sha256
           WHERE e.error IS NULL AND e.n_chars > 0 AND COALESCE(s.complete, 0) = 0
           ORDER BY e.n_chars, f.id"""
    ).fetchall()


def _drop_file(conn, file_id):
    conn.execute("DELETE FROM chunks_fts WHERE rowid IN (SELECT id FROM chunks WHERE file_id = ?)", (file_id,))
    conn.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))


def _index_file(conn, model, f, log):
    state = conn.execute("SELECT sha256, done_page FROM index_state WHERE file_id = ?", (f["id"],)).fetchone()
    if state is None or state["sha256"] != f["sha256"]:  # new file or new version: start over
        _drop_file(conn, f["id"])
        conn.execute("INSERT OR REPLACE INTO index_state VALUES (?, ?, 0, 0)", (f["id"], f["sha256"]))
        conn.commit()
        done = 0
    else:
        done = state["done_page"]
    pages = conn.execute(
        "SELECT page, text FROM pages WHERE file_id = ? AND page > ? ORDER BY page", (f["id"], done)).fetchall()
    total = 0
    for i in range(0, len(pages), PAGE_BATCH):
        batch = pages[i:i + PAGE_BATCH]
        pieces = [(r["page"], c) for r in batch for c in split_page(r["text"])]
        # embed before touching the database, so the write transaction stays short
        vectors = list(model.embed([c for _, c in pieces], batch_size=16)) if pieces else []
        for (page, text), vec in zip(pieces, vectors):
            vec = np.asarray(vec, dtype=np.float32)
            vec /= np.linalg.norm(vec) or 1.0
            cur = conn.execute(
                "INSERT INTO chunks (file_id, sha256, page, text, embedding) VALUES (?, ?, ?, ?, ?)",
                (f["id"], f["sha256"], page, text, vec.tobytes()))
            conn.execute("INSERT INTO chunks_fts (rowid, text) VALUES (?, ?)", (cur.lastrowid, text))
        conn.execute("UPDATE index_state SET done_page = ? WHERE file_id = ?", (batch[-1]["page"], f["id"]))
        conn.commit()
        total += len(pieces)
        if len(pages) > PAGE_BATCH:
            log(f"    {f['filename']}: page {batch[-1]['page']}/{f['n_pages']}")
    conn.execute("UPDATE index_state SET complete = 1 WHERE file_id = ?", (f["id"],))
    conn.commit()
    return total


def index_pending(conn, log=print):
    stats = {"files": 0, "chunks": 0}
    todo = pending_files(conn)
    if not todo:
        return stats
    model = _embedder()
    for f in todo:
        n = _index_file(conn, model, f, log)
        stats["files"] += 1
        stats["chunks"] += n
        log(f"  indexed {n:>5} chunks  {f['filename']}")
    return stats


# ---------------------------------------------------------------- retrieval

_STOP = set("a an the of to in on for and or is are was be by with as at from that this what how why "
            "which when does do can it its into about between".split())


def _fts_query(text):
    words = [w for w in re.findall(r"[A-Za-z0-9+#]+", text.lower()) if len(w) > 1 and w not in _STOP]
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words))


def _course_filter(course_id):
    if course_id is None:
        return "", ()
    return (" AND c.file_id IN (SELECT f.id FROM files f JOIN activities a ON a.id = f.activity_id"
            " WHERE a.course_id = ?)", (course_id,))


def _keyword_ranks(conn, query, course_id):
    match = _fts_query(query)
    if not match:
        return []
    where, params = _course_filter(course_id)
    rows = conn.execute(
        f"""SELECT c.id FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid
            WHERE chunks_fts MATCH ? {where} ORDER BY bm25(chunks_fts) LIMIT ?""",
        (match, *params, _CANDIDATES))
    return [r["id"] for r in rows]


def _vector_ranks(conn, query, course_id):
    where, params = _course_filter(course_id)
    rows = conn.execute(f"SELECT c.id, c.embedding FROM chunks c WHERE 1=1 {where}", params).fetchall()
    if not rows:
        return []
    matrix = np.frombuffer(b"".join(r["embedding"] for r in rows), dtype=np.float32).reshape(len(rows), -1)
    q = np.asarray(next(iter(_embedder().query_embed([query]))), dtype=np.float32)
    q /= np.linalg.norm(q) or 1.0
    best = np.argsort(-(matrix @ q))[:_CANDIDATES]
    return [rows[i]["id"] for i in best]


_PAGE_NUMBER_END = re.compile(r"(\.{2,}|\s)\d{1,4}\s*$")
_SECTION_START = re.compile(r"^\s*\d+(\.\d+)+\s")
NAVIGATION_PENALTY = 0.3


def is_navigation(text):
    """Table of contents, index or course-schedule text: lists of headings / page numbers, no content."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 6:
        return False
    numbered = sum(bool(_PAGE_NUMBER_END.search(line) or _SECTION_START.match(line)) for line in lines)
    return numbered / len(lines) >= 0.3


def search(conn, query, course_id=None, k=TOP_K):
    """Reciprocal-rank fusion of keyword and vector results; at most 2 chunks per page.

    Navigation pages (tables of contents, indexes, schedules) mention every topic by name and
    would otherwise outrank the pages that actually explain it, so their score is damped.
    """
    scores = {}
    for ranking in (_keyword_ranks(conn, query, course_id), _vector_ranks(conn, query, course_id)):
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (_RRF_K + rank)
    rows = {}
    for cid in scores:
        row = conn.execute(
            """SELECT c.id, c.file_id, c.page, c.text, f.filename, a.name AS activity,
                      co.id AS course_id, co.name AS course
               FROM chunks c JOIN files f ON f.id = c.file_id
               JOIN activities a ON a.id = f.activity_id JOIN courses co ON co.id = a.course_id
               WHERE c.id = ?""", (cid,)).fetchone()
        rows[cid] = row
        if is_navigation(row["text"]):
            scores[cid] *= NAVIGATION_PENALTY
    results, per_page = [], {}
    for cid in sorted(scores, key=scores.get, reverse=True):
        row = rows[cid]
        key = (row["file_id"], row["page"])
        if per_page.get(key, 0) >= 2:
            continue
        per_page[key] = per_page.get(key, 0) + 1
        results.append(dict(row) | {"score": scores[cid]})
        if len(results) == k:
            break
    return results


# ---------------------------------------------------------------- answering

_REWRITE_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
    "additionalProperties": False,
}

_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "cited": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["answer", "cited"],
    "additionalProperties": False,
}

_REWRITE_SYSTEM = (
    "A first-year student at INHA University in Tashkent asks about English course materials. "
    "The question is usually in Uzbek (Latin script), sometimes Russian or English. Translate every "
    "subject term into the standard English academic term used in textbooks (e.g. hosila -> derivative, "
    "boshlang'ich funksiya -> antiderivative, uzluksizlik -> continuity, to'plam -> set, "
    "massiv -> array, sinf -> class, merosxo'rlik -> inheritance, sanoq sistemasi -> number system). "
    "Return one English search query of 4-12 words phrased like the question itself, e.g. "
    "'definition of the derivative of a function' or 'difference between prefix and postfix "
    "increment in C++'. Never add words unrelated to the question."
)

_ANSWER_SYSTEM = (
    "You answer a university student's question using ONLY the numbered course passages given. "
    "Answer in the same language as the question (Uzbek questions: Uzbek, Latin script), keeping "
    "technical terms in English in parentheses where helpful. Cite passages inline as [1], [2]. "
    "Passages may come from OCR: repair broken formulas when the intent is clear. If the passages "
    "do not contain the answer, say so plainly instead of guessing. Put the numbers of the "
    "passages you used in `cited`."
)


def answer(conn, provider, question, course_id=None, k=TOP_K):
    course = conn.execute("SELECT name FROM courses WHERE id = ?", (course_id,)).fetchone() if course_id else None
    prompt = f"Course: {course['name']}\nQuestion: {question}" if course else question
    query = provider.complete_json(_REWRITE_SYSTEM, prompt, _REWRITE_SCHEMA, max_tokens=300)["query"]
    passages = search(conn, query, course_id, k)
    if not passages:
        return {"answer": "Materiallarda mos ma'lumot topilmadi.", "query": query, "sources": []}
    context = "\n\n".join(
        f"[{i}] {p['course']} / {p['filename']}, page {p['page']}\n{p['text']}"
        for i, p in enumerate(passages, 1))
    result = provider.complete_json(
        _ANSWER_SYSTEM, f"Passages:\n{context}\n\nQuestion: {question}", _ANSWER_SCHEMA, max_tokens=1500)
    cited = [n for n in dict.fromkeys(result["cited"]) if 1 <= n <= len(passages)]
    sources = [{"n": n, **{key: passages[n - 1][key] for key in
                           ("course", "activity", "filename", "file_id", "page", "text")}}
               for n in (cited or range(1, len(passages) + 1))]
    return {"answer": result["answer"], "query": query, "sources": sources}
