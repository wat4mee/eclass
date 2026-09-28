"""Ask a question about your course materials; the answer cites file and page.

    python ask.py "limit ta'rifi nima?"
    python ask.py "operator overloading nima?" --course 2562
    python ask.py --index            # index new/changed files (resumable)
"""
import argparse
import sys
from pathlib import Path

from eclass import db, rag
from eclass.ai import AIError, get_provider
from eclass.lock import exclusive_run

DATA_DIR = Path(__file__).resolve().parent / "data"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="?")
    ap.add_argument("--course", type=int, help="limit the search to one course id")
    ap.add_argument("--index", action="store_true", help="index new/changed files")
    ap.add_argument("--db", default=str(DATA_DIR / "eclass.db"))
    args = ap.parse_args()
    if not args.question and not args.index:
        ap.error("give a question or --index")

    conn = db.connect(args.db)
    if args.index:
        with exclusive_run(DATA_DIR / ".run.lock"):
            print(rag.index_pending(conn))
        if not args.question:
            return 0

    try:
        result = rag.answer(conn, get_provider(), args.question, course_id=args.course)
    except AIError as exc:
        print(f"AI error: {exc}", file=sys.stderr)
        return 1
    print(result["answer"])
    print(f"\n(search: {result['query']})")
    for s in result["sources"]:
        print(f"  [{s['n']}] {s['course']} / {s['filename']}, p. {s['page']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
