"""Study material generation: summary, key concepts, flashcards and a 5-question quiz.

Sized for Groq's free tier (8K tokens/minute): texts longer than CHUNK_CHARS are
first condensed chunk by chunk into English notes (map), and the study pack is
generated from those notes (reduce). Chunk notes are stored, so a run that hits
the daily quota resumes where it stopped.
"""
import json
import os

from . import db
from .ai import DailyLimitReached

CHUNK_CHARS = 10_000      # ~3K tokens: prompt + answer must fit into 8K tokens/minute
MAX_AI_CHARS = 150_000    # longer files are textbooks: kept for search (stage 4), not summarized
MIN_AI_CHARS = 300
LANGUAGES = {"uz": "Uzbek (Latin script)", "en": "English", "ru": "Russian"}

NOTES_SCHEMA = {
    "type": "object",
    "properties": {"notes": {"type": "string"}},
    "required": ["notes"],
    "additionalProperties": False,
}

STUDY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_concepts": {"type": "array", "items": {
            "type": "object",
            "properties": {"term": {"type": "string"}, "explanation": {"type": "string"}},
            "required": ["term", "explanation"], "additionalProperties": False}},
        "flashcards": {"type": "array", "items": {
            "type": "object",
            "properties": {"front": {"type": "string"}, "back": {"type": "string"}},
            "required": ["front", "back"], "additionalProperties": False}},
        "quiz": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}},
                "answer_index": {"type": "integer"},
                "explanation": {"type": "string"}},
            "required": ["question", "options", "answer_index", "explanation"],
            "additionalProperties": False}},
    },
    "required": ["summary", "key_concepts", "flashcards", "quiz"],
    "additionalProperties": False,
}

NOTES_SYSTEM = (
    "You condense university course material into dense study notes. Keep every "
    "definition, theorem, formula, algorithm and worked example; drop filler. The text "
    "may come from OCR, so repair obviously broken formulas when the intent is clear. "
    "Write in English, at most 350 words, plain text."
)


def study_system(language):
    return (
        "You are a study assistant for a first-year student at INHA University in Tashkent. "
        f"Write everything in {language}; keep standard technical terms in English in "
        "parentheses where it helps. Use only what is in the material - never invent topics; "
        "every flashcard and quiz question must be answerable from the material itself. "
        "The text may come from OCR: silently repair broken formulas when the intent is clear.\n"
        "Write every formula in LaTeX inside $...$ (e.g. $\\lim_{x \\to a} f(x) = L$, $\\frac{dy}{dx}$). "
        "Write naturally, not word for word; keep technical terms such as limit, derivative, class in English; "
        "in Uzbek use correct Latin-script forms (e.g. 'ingliz matematigi', o' and g' with apostrophes).\n"
        "Produce:\n"
        "- summary: 120-250 words, the main ideas in logical order\n"
        "- key_concepts: 5-8 items, each a term and a 1-2 sentence explanation\n"
        "- flashcards: 8 question/answer cards for active recall\n"
        "- quiz: exactly 5 multiple-choice questions, each with exactly 4 options, "
        "answer_index 0-3 pointing to the correct option, and a short explanation"
    )


def language():
    code = os.getenv("STUDY_LANGUAGE", "uz").lower()
    return code, LANGUAGES.get(code, code)


def pending(conn, force=False):
    """Extracted materials and assignment files (not textbooks - see chapters.py) without a current study pack."""
    stale = "" if force else "AND (s.file_id IS NULL OR s.sha256 != f.sha256)"
    return conn.execute(
        f"""SELECT f.id, f.filename, f.sha256, e.n_chars, e.n_pages,
                   a.name AS activity, c.name AS course
            FROM files f
            JOIN extractions e ON e.file_id = f.id AND e.sha256 = f.sha256
            JOIN activities a ON a.id = f.activity_id
            JOIN courses c ON c.id = a.course_id
            LEFT JOIN study s ON s.file_id = f.id
            WHERE e.error IS NULL
              AND e.n_chars BETWEEN ? AND ? {stale}
            ORDER BY c.name, a.section, f.id""",
        (MIN_AI_CHARS, MAX_AI_CHARS),
    ).fetchall()


def file_text(conn, file_id):
    rows = conn.execute(
        "SELECT page, text FROM pages WHERE file_id = ? AND text != '' ORDER BY page", (file_id,)
    )
    return [(r["page"], r["text"]) for r in rows]


def chunk_pages(pages, limit=CHUNK_CHARS):
    """Group '[Page N]' blocks into chunks of at most `limit` characters."""
    chunks, current = [], ""
    for number, text in pages:
        block = f"[Page {number}]\n{text}\n"
        while len(block) > limit:  # a single huge page: hard split
            if current:
                chunks.append(current)
                current = ""
            chunks.append(block[:limit])
            block = block[limit:]
        if current and len(current) + len(block) > limit:
            chunks.append(current)
            current = ""
        current += block
    if current:
        chunks.append(current)
    return chunks


def _notes_for(conn, provider, f, chunks, log, offset=0):
    """Map step, resumable: notes for chunk i are stored under chunk number offset + i."""
    done = {r["chunk"] - offset: r["notes"] for r in conn.execute(
        "SELECT chunk, notes FROM study_notes WHERE file_id = ? AND sha256 = ? AND chunk >= ? AND chunk < ?",
        (f["id"], f["sha256"], offset, offset + 100_000))}
    notes = []
    for i, chunk in enumerate(chunks):
        if i not in done:
            log(f"      notes {i + 1}/{len(chunks)}")
            result = provider.complete_json(
                NOTES_SYSTEM, f"Course: {f['course']}\nFile: {f['filename']}\n\n{chunk}",
                NOTES_SCHEMA, max_tokens=1500)
            done[i] = result["notes"]
            conn.execute("INSERT OR REPLACE INTO study_notes VALUES (?, ?, ?, ?)",
                         (f["id"], f["sha256"], offset + i, done[i]))
            conn.commit()
        notes.append(done[i])
    return "\n\n".join(f"[Part {i + 1}]\n{n}" for i, n in enumerate(notes))


def clean_result(result):
    """Drop malformed quiz items; the schema cannot enforce counts or ranges."""
    quiz = [q for q in result["quiz"]
            if len(q["options"]) == 4 and 0 <= q["answer_index"] < 4 and q["question"].strip()]
    return {**result, "quiz": quiz[:5]}


def build_pack(conn, provider, f, pages, log=print, notes_offset=0):
    """Study pack (not saved) from (page, text) pairs; long texts are condensed chunk by chunk first."""
    chunks = chunk_pages(pages)
    if not chunks:
        raise ValueError("no text to study")
    material = chunks[0] if len(chunks) == 1 else _notes_for(conn, provider, f, chunks, log, notes_offset)
    while len(material) > CHUNK_CHARS:  # extremely long notes: condense once more
        material = "\n\n".join(
            provider.complete_json(NOTES_SYSTEM, part, NOTES_SCHEMA, max_tokens=1500)["notes"]
            for part in chunk_pages([(0, material)]))
    code, lang_name = language()
    user = f"Course: {f['course']}\nMaterial: {f['activity']} ({f['filename']})\n\n{material}"
    return code, clean_result(provider.complete_json(study_system(lang_name), user, STUDY_SCHEMA, max_tokens=4000))


def generate(conn, provider, f, log=print):
    code, result = build_pack(conn, provider, f, file_text(conn, f["id"]), log)
    db.save_study(conn, f["id"], f["sha256"], provider.name, provider.model, code, result)
    return result


def plan(conn, force=False):
    """(file row, number of chunks) for everything pending - no API calls."""
    return [(f, len(chunk_pages(file_text(conn, f["id"])))) for f in pending(conn, force)]


def generate_pending(conn, provider, limit=None, force=False, log=print):
    stats = {"generated": 0, "failed": 0, "remaining": 0}
    todo = pending(conn, force)
    for n, f in enumerate(todo):
        if limit is not None and stats["generated"] >= limit:
            stats["remaining"] = len(todo) - n
            break
        log(f"  [{f['course']}] {f['activity']} ({f['n_chars']} chars)")
        try:
            result = generate(conn, provider, f, log)
            stats["generated"] += 1
            log(f"      ok: {len(result['key_concepts'])} concepts, "
                f"{len(result['flashcards'])} cards, {len(result['quiz'])} quiz")
        except DailyLimitReached as exc:
            stats["remaining"] = len(todo) - n
            log(f"      daily limit reached - {stats['remaining']} file(s) left for the next run ({exc})")
            break
        except Exception as exc:  # one bad file must not stop the queue
            stats["failed"] += 1
            log(f"      FAIL {type(exc).__name__}: {exc}")
    return stats


TRANSLATE_SYSTEM = (
    "You translate a university study pack, given as JSON, into {language}. Translate every string value "
    "naturally rather than word for word; keep technical terms, code, numbers and formulas unchanged "
    "(formulas stay inside $...$ if present). Keep the same number of items, the same option order and the "
    "same answer_index values. Do not add, drop or merge content."
)


def translate_pack(conn, provider, file_id, code):
    """Translate a stored study pack into another dashboard language and cache it."""
    row = conn.execute("SELECT * FROM study WHERE file_id = ?", (file_id,)).fetchone()
    if row is None:
        raise LookupError(f"no study pack for file {file_id}")
    pack = {"summary": row["summary"], "key_concepts": json.loads(row["concepts"]),
            "flashcards": json.loads(row["flashcards"]), "quiz": json.loads(row["quiz"])}
    result = provider.complete_json(
        TRANSLATE_SYSTEM.format(language=LANGUAGES.get(code, code)),
        json.dumps(pack, ensure_ascii=False), STUDY_SCHEMA, max_tokens=4500)
    for new, old in zip(result["quiz"], pack["quiz"]):  # the answer key must survive translation
        new["answer_index"] = old["answer_index"]
    result = clean_result(result)
    db.save_translation(conn, file_id, code, row["sha256"], result)
    return result
