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
        return [], {}
    matrix = np.frombuffer(b"".join(r["embedding"] for r in rows), dtype=np.float32).reshape(len(rows), -1)
    q = np.asarray(next(iter(_embedder().query_embed([query]))), dtype=np.float32)
    q /= np.linalg.norm(q) or 1.0
    sims = matrix @ q
    best = np.argsort(-sims)[:_CANDIDATES]
    return [rows[i]["id"] for i in best], {rows[i]["id"]: float(sims[i]) for i in range(len(rows))}


_PAGE_NUMBER_END = re.compile(r"(\.{2,}|\s)(\d{1,4}|[ivxlc]{1,7})\s*$")  # arabic or roman page numbers
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
    vector_ranking, sims = _vector_ranks(conn, query, course_id)
    for ranking in (_keyword_ranks(conn, query, course_id), vector_ranking):
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
    # fusion picks the candidates (keywords help recall); meaning decides their order
    shortlist = sorted(scores, key=scores.get, reverse=True)[:k * 2]
    shortlist.sort(key=lambda cid: sims.get(cid, 0.0) * (NAVIGATION_PENALTY if is_navigation(rows[cid]["text"]) else 1),
                   reverse=True)
    results, per_page = [], {}
    for cid in shortlist:
        row = rows[cid]
        key = (row["file_id"], row["page"])
        if per_page.get(key, 0) >= 2:
            continue
        per_page[key] = per_page.get(key, 0) + 1
        results.append(dict(row) | {"score": scores[cid], "sim": sims.get(cid, 0.0)})
        if len(results) == k:
            break
    return results


# ---------------------------------------------------------------- answering

MIN_SIM = 0.68       # cosine similarity: on-topic passages score ~0.75+, unrelated questions stay below ~0.62
SIM_WINDOW = 0.10    # keep passages close to the best match only
MAX_SOURCES = 3
HISTORY_TURNS = 4

_CONTEXT_SCHEMA = {
    "type": "object",
    "properties": {"standalone": {"type": "string"}, "query": {"type": "string"}},
    "required": ["standalone", "query"],
    "additionalProperties": False,
}

_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "found": {"type": "boolean"},
        "cited": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["answer", "found", "cited"],
    "additionalProperties": False,
}

_REWRITE_SYSTEM = (
    "A first-year student at INHA University in Tashkent chats about English course materials, usually in "
    "Uzbek (Latin script), sometimes in Russian or English. Given the conversation and the latest message:\n"
    "1. standalone: rewrite the latest message so it is fully understandable without the conversation - "
    "resolve references such as 'unga', 'bu', 'uni', 'it', 'that', 'его', 'это' using the previous turns. Keep the "
    "student's language. If it already stands alone, copy it unchanged.\n"
    "2. query: one English search query of 4-12 words phrased like the standalone question, translating subject "
    "terms into the standard English textbook terms (e.g. hosila -> derivative, boshlang'ich funksiya -> "
    "antiderivative, uzluksizlik -> continuity, to'plam -> set, massiv -> array, sinf -> class, merosxo'rlik -> "
    "inheritance, sanoq sistemasi -> number system). Never add words unrelated to the question."
)


def _answer_system(language):
    return (
        "You are Shahzod AI, a study assistant for a first-year university student. Answer using ONLY the "
        f"numbered course passages provided. Write the answer in {language}.\n"
        "Style: short and clear - 2 to 6 sentences, or a few bullet points for lists. Explain simply, not word for "
        "word. Keep technical terms in English where students use them (limit, derivative, class, pointer), "
        "optionally followed by a brief explanation. When writing Uzbek use correct Latin-script forms and natural "
        "phrasing, e.g. 'ingliz matematigi', 'ingliz olimi', with the apostrophes in o' and g'.\n"
        "Write every formula in LaTeX inside $...$ (for example $\\lim_{x \\to a} f(x) = L$, $\\frac{dy}{dx}$); use "
        "$$...$$ only for a formula on its own line.\n"
        "Cite the passages you use inline as [1], [2]. Passages may come from OCR: repair broken formulas when the "
        "intent is clear. Be helpful: if the passages contain relevant material - a definition, a worked example, a "
        "theorem - build the answer from it (a textbook example counts as an example even if it is not the simplest "
        "one). Only when the passages are unrelated to the question set found to false, leave cited empty and say "
        "in one sentence that the materials do not cover it."
    )


def _history_text(history):
    lines = []
    for turn in (history or [])[-HISTORY_TURNS:]:
        q, a = str(turn.get("q", "")).strip(), str(turn.get("a", "")).strip()
        if q:
            lines.append(f"Student: {q[:500]}")
        if a:
            lines.append(f"Assistant: {a[:600]}")
    return "\n".join(lines)


def _group_sources(passages, cited):
    """Merge cited passages from the same file and nearby pages; returns groups and old->new numbering."""
    groups, renumber = [], {}
    for n in cited:
        p = passages[n - 1]
        for g in groups:
            if g["file_id"] == p["file_id"] and min(abs(p["page"] - x) for x in g["pages"]) <= 2:
                g["pages"] = sorted(set(g["pages"]) | {p["page"]})
                renumber[n] = g["n"]
                break
        else:
            if len(groups) == MAX_SOURCES:
                continue
            groups.append({"n": len(groups) + 1, "file_id": p["file_id"], "filename": p["filename"],
                           "course": p["course"], "activity": p["activity"], "pages": [p["page"]],
                           "page": p["page"], "text": p["text"]})
            renumber[n] = len(groups)
    return groups, renumber


def _renumber_citations(text, renumber):
    def swap(m):
        new = renumber.get(int(m.group(1)))
        return f"[{new}]" if new else ""
    text = re.sub(r"\[(\d+)\]", swap, text)
    text = re.sub(r"(\[\d+\])(?:\s*\1)+", r"\1", text)  # [1][1] -> [1]
    return re.sub(r"[ \t]+([.,;:])", r"\1", text)


def answer(conn, provider, question, course_id=None, k=TOP_K, language="Uzbek (Latin script)",
           history=None, not_found="Materiallarda bu haqida ma'lumot topilmadi."):
    """Answer a question (with optional chat history) from the course materials.

    Returns {answer, found, standalone, query, sources}; sources is empty when nothing relevant was found.
    """
    convo = _history_text(history)
    prompt = (f"Conversation so far:\n{convo}\n\n" if convo else "") + f"Latest message: {question}"
    if course_id:
        course = conn.execute("SELECT name FROM courses WHERE id = ?", (course_id,)).fetchone()
        if course:
            prompt = f"Course: {course['name']}\n{prompt}"
    ctx = provider.complete_json(_REWRITE_SYSTEM, prompt, _CONTEXT_SCHEMA, max_tokens=400)
    standalone, query = ctx["standalone"].strip() or question, ctx["query"]

    passages = search(conn, query, course_id, k)
    top = max((p["sim"] for p in passages), default=0.0)
    passages = [p for p in passages if p["sim"] >= MIN_SIM and p["sim"] >= top - SIM_WINDOW]
    empty = {"answer": not_found, "found": False, "standalone": standalone, "query": query, "sources": []}
    if not passages:
        return empty

    context = "\n\n".join(
        f"[{i}] {p['course']} / {p['filename']}, page {p['page']}\n{p['text']}" for i, p in enumerate(passages, 1))
    user = f"Passages:\n{context}\n\n" + (f"Conversation so far:\n{convo}\n\n" if convo else "") + \
           f"Question: {standalone}"
    result = provider.complete_json(_answer_system(language), user, _ANSWER_SCHEMA, max_tokens=1500)
    cited = [n for n in dict.fromkeys(result["cited"]) if 1 <= n <= len(passages)]
    if not result["found"] or not cited:
        return empty | ({"answer": result["answer"]} if result["answer"].strip() else {})
    groups, renumber = _group_sources(passages, cited)
    return {"answer": _renumber_citations(result["answer"], renumber), "found": True,
            "standalone": standalone, "query": query, "sources": groups}
