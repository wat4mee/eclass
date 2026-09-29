"""Full-text search of course material text in Postgres, only in the courses the student is enrolled in.

Used by the AI chat instead of the Mac version's local embeddings (too heavy for a small server). The chat first
rewrites the question into an English search query; a page counts as relevant when it matches at least two of the
query's words (or the only one), so a page that merely mentions one common word is not offered as a source.
"""
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

MAX_TERMS = 12
_WORD = re.compile(r"[a-z0-9]+")
_EXCERPT = 'StartSel="", StopSel="", MaxFragments=3, MaxWords=60, MinWords=25, FragmentDelimiter=" … "'
_SQL = text("""
    WITH q AS (SELECT to_tsquery('english', :query) AS q),
         terms AS (SELECT plainto_tsquery('english', w) AS t FROM unnest(CAST(:words AS text[])) AS w
                   WHERE plainto_tsquery('english', w)::text <> '')
    SELECT mp.material_id, mp.page, m.filename, a.name AS activity, c.id AS course_id, c.name AS course,
           ts_headline('english', mp.text, q.q, :excerpt) AS passage,
           (SELECT count(*) FROM terms WHERE mp.tsv @@ terms.t) AS matched,
           (SELECT count(*) FROM terms) AS wanted
    FROM q, material_pages mp
    JOIN materials m ON m.id = mp.material_id
    JOIN activities a ON a.id = m.activity_id
    JOIN courses c ON c.id = a.course_id
    JOIN enrollments e ON e.course_id = c.id AND e.user_id = :user_id
    WHERE mp.tsv @@ q.q AND (CAST(:course_id AS integer) IS NULL OR c.id = :course_id)
    ORDER BY matched DESC, ts_rank_cd(mp.tsv, q.q, 32) DESC
    LIMIT :limit""")


def passages(db: Session, user_id: int, query: str, course_id: int | None = None, k: int = 8) -> list[dict]:
    """Best-matching pages as chat passages (the shape eclass.rag.answer expects)."""
    words = list(dict.fromkeys(_WORD.findall((query or "").lower())))[:MAX_TERMS]
    if not words:
        return []
    rows = db.execute(_SQL, {"query": " | ".join(words), "words": words, "excerpt": _EXCERPT,
                             "user_id": user_id, "course_id": course_id, "limit": k * 3}).mappings().all()
    found = [r for r in rows if r["matched"] >= min(2, r["wanted"])][:k]
    return [{"file_id": r["material_id"], "page": r["page"], "text": r["passage"], "filename": r["filename"],
             "activity": r["activity"], "course_id": r["course_id"], "course": r["course"], "sim": 1.0}
            for r in found]
