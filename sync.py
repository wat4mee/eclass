"""Sync eClass courses, activities, files and assignments into SQLite + data/files.

    python sync.py --course 2539            # one course (repeatable)
    python sync.py --all                    # every course on the dashboard
    python sync.py --course 2539 --refresh  # re-check already downloaded files
    python sync.py --all --no-notify        # sync without Telegram notifications
    python sync.py --all --no-ai            # sync + text extraction, no AI study packs
"""
import argparse
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from eclass import db, extract, notify, rag, study, telegram
from eclass.activities import (
    SUPPORTED_TYPES,
    parse_activity,
    parse_assign,
    pluginfile_links,
    resolve_url,
)
from eclass.ai import AIError, get_provider
from eclass.auth import EClassClient
from eclass.lock import exclusive_run
from eclass.courses import list_courses, parse_course_page
from eclass.files import download_links, download_ubfile, safe_name, section_dir

DATA_DIR = Path(__file__).resolve().parent / "data"


def process_activity(client, conn, act, dest_dir, refresh, stats):
    kind = act["type"]
    if kind == "ubfile":
        results = download_ubfile(client, conn, act, dest_dir, refresh)
    elif kind == "folder":
        links = pluginfile_links(client.soup(act["url"]))
        results = download_links(client, conn, act["id"], links, dest_dir / safe_name(act["name"]), refresh)
    elif kind == "assign":
        info, attachments = parse_assign(client.soup(act["url"]))
        db.upsert_assignment(conn, act["id"], info)
        stats["assignments"] += 1
        print(f"      due={info['due_date']} | {info['submission_status']} | "
              f"{info['grading_status']} | grade={info['grade']}")
        results = download_links(client, conn, act["id"], attachments, dest_dir / safe_name(act["name"]), refresh)
    else:
        return
    for r in results:
        stats[f"files_{r}"] += 1
    if results:
        print(f"      files: {dict(Counter(results))}")


def resolve_external_url(client, conn, act, refresh):
    """url activities: store the external target; reuse the stored one unless refreshing."""
    own_host = urlparse(client.base_url).netloc
    prev = conn.execute("SELECT url FROM activities WHERE id = ?", (act["id"],)).fetchone()
    if prev and prev["url"] and urlparse(prev["url"]).netloc != own_host and not refresh:
        return prev["url"]
    return resolve_url(client, act["url"]) or act["url"]


def sync_course(client, conn, course, files_root, refresh, stats):
    db.upsert_course(conn, course)
    sections = parse_course_page(client.soup(f"/course/view.php?id={course['id']}"))
    print(f"\n== {course['id']} {course['name']}: {len(sections)} sections")
    for sec in sections:
        db.upsert_section(conn, course["id"], sec["number"], sec["name"])
        stats["sections"] += 1
        dest = section_dir(files_root, course["name"], sec["number"], sec["name"])
        for li in sec["activities"]:
            act = parse_activity(li, course["id"], sec["number"])
            if act is None:
                continue
            try:
                if act["type"] == "url" and act["url"]:
                    act["url"] = resolve_external_url(client, conn, act, refresh)
                is_new = db.upsert_activity(conn, act)
                stats["activities"] += 1
                stats[f"type_{act['type']}"] += 1
                stats["activities_new"] += is_new
                print(f"  [{sec['number']:02d}] {act['type']:<8} {act['id']} {act['name']}"
                      f"{'  (NEW)' if is_new else ''}")
                if act["type"] in SUPPORTED_TYPES and act["url"]:
                    process_activity(client, conn, act, dest, refresh, stats)
            except Exception as exc:  # one broken activity must not stop the sync
                stats["errors"] += 1
                print(f"      ERROR in {act['type']} {act['id']}: {type(exc).__name__}: {exc}")
            conn.commit()


def main():
    with exclusive_run(DATA_DIR / ".run.lock"):
        return _main()


def _main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--course", type=int, action="append", help="course id (repeatable)")
    ap.add_argument("--all", action="store_true", help="sync every course on the dashboard")
    ap.add_argument("--refresh", action="store_true",
                    help="re-fetch known files/links; unchanged files (same sha256) are not rewritten")
    ap.add_argument("--no-notify", action="store_true", help="skip Telegram notifications")
    ap.add_argument("--no-ai", action="store_true", help="skip AI study packs (text is still extracted)")
    ap.add_argument("--db", default=str(DATA_DIR / "eclass.db"))
    ap.add_argument("--files-dir", default=str(DATA_DIR / "files"))
    args = ap.parse_args()
    if not args.course and not args.all:
        ap.error("pass --course ID (repeatable) or --all")

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(args.db)
    client = EClassClient()
    client.login()
    print("login OK")

    courses = list_courses(client)
    if args.course:
        wanted = set(args.course)
        missing = wanted - {c["id"] for c in courses}
        if missing:
            print(f"not on dashboard: {sorted(missing)}", file=sys.stderr)
        courses = [c for c in courses if c["id"] in wanted]

    stats = Counter()
    for course in courses:
        sync_course(client, conn, course, Path(args.files_dir), args.refresh, stats)

    print("\nextracting text...")
    print(" ", extract.extract_pending(conn))
    print("indexing for Q&A...")
    print(" ", rag.index_pending(conn, log=lambda *_: None))
    if not args.no_ai:
        try:
            provider = get_provider()
            print(f"study packs ({provider.name} {provider.model})...")
            ai_stats = study.generate_pending(conn, provider)
            stats["errors"] += ai_stats["failed"]
            print(" ", ai_stats)
        except AIError as exc:
            print(f"  AI skipped: {exc}")

    if not args.no_notify:
        try:
            print(notify.run(conn))
        except telegram.TelegramError as exc:
            stats["errors"] += 1
            print(f"telegram error: {exc}", file=sys.stderr)
    conn.close()

    types = ", ".join(f"{k[5:]}={v}" for k, v in sorted(stats.items()) if k.startswith("type_"))
    print("\n=== Report ===")
    print(f"courses:     {len(courses)}")
    print(f"sections:    {stats['sections']}")
    print(f"activities:  {stats['activities']} (new {stats['activities_new']}; {types})")
    print(f"files:       downloaded {stats['files_new'] + stats['files_updated']} "
          f"(new {stats['files_new']}, updated {stats['files_updated']}), "
          f"already present {stats['files_skipped'] + stats['files_unchanged']}")
    print(f"assignments: {stats['assignments']}")
    print(f"errors:      {stats['errors']}")
    print(f"requests:    {client.request_count}")
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
