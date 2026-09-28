"""Extract text from downloaded files and generate study packs with AI.

    python analyze.py               # extract new files, then generate pending study packs
    python analyze.py --plan        # show what would be sent to the AI (no API calls)
    python analyze.py --limit 3     # generate at most 3 study packs
    python analyze.py --extract-only
    python analyze.py --show FILE_ID
"""
import argparse
import json
import sys
from pathlib import Path

from eclass import db, extract, study
from eclass.ai import AIError, get_provider

DATA_DIR = Path(__file__).resolve().parent / "data"


def show(conn, file_id):
    row = conn.execute(
        "SELECT s.*, f.filename FROM study s JOIN files f ON f.id = s.file_id WHERE s.file_id = ?",
        (file_id,)).fetchone()
    if row is None:
        print(f"no study pack for file {file_id}")
        return 1
    print(f"# {row['filename']}  ({row['provider']} {row['model']}, {row['language']})\n")
    print(row["summary"], "\n\n## Key concepts")
    for c in json.loads(row["concepts"]):
        print(f"- {c['term']}: {c['explanation']}")
    print("\n## Flashcards")
    for c in json.loads(row["flashcards"]):
        print(f"- Q: {c['front']}\n  A: {c['back']}")
    print("\n## Quiz")
    for i, q in enumerate(json.loads(row["quiz"]), 1):
        print(f"{i}. {q['question']}")
        for j, opt in enumerate(q["options"]):
            print(f"   {'*' if j == q['answer_index'] else ' '} {'ABCD'[j]}) {opt}")
        print(f"   -> {q['explanation']}")
    return 0


def print_plan(conn, force):
    items = study.plan(conn, force)
    calls = sum(n + (n > 1) for _, n in items)
    chars = sum(f["n_chars"] for f, _ in items)
    for f, n in items:
        print(f"  {f['id']:>4} {f['n_chars']:>7} chars {n:>2} chunk(s)  [{f['course']}] {f['activity']}")
    # rough: 1 token ~ 3.5 chars of input; ~1.5K output per notes call, ~3K per study pack
    est = chars / 3.5 + sum((n > 1) * n * 1500 + 3000 for _, n in items)
    print(f"\n{len(items)} file(s), {calls} API call(s), ~{est / 1000:.0f}K tokens total")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", action="store_true", help="list pending files and estimated tokens")
    ap.add_argument("--extract-only", action="store_true")
    ap.add_argument("--limit", type=int, help="max study packs to generate in this run")
    ap.add_argument("--force", action="store_true", help="regenerate even if up to date")
    ap.add_argument("--show", type=int, metavar="FILE_ID", help="print a stored study pack")
    ap.add_argument("--db", default=str(DATA_DIR / "eclass.db"))
    args = ap.parse_args()

    conn = db.connect(args.db)
    if args.show is not None:
        return show(conn, args.show)

    print("extracting text...")
    print(" ", extract.extract_pending(conn))
    if args.extract_only:
        return 0
    if args.plan:
        print_plan(conn, args.force)
        return 0

    try:
        provider = get_provider()
    except AIError as exc:
        print(f"AI skipped: {exc}", file=sys.stderr)
        return 1
    print(f"generating study packs with {provider.name} ({provider.model})...")
    stats = study.generate_pending(conn, provider, limit=args.limit, force=args.force)
    print(" ", stats)
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
