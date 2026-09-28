"""Change notifications: new material, new assignment, deadline < 24h, new grade.

Events are derived from the database state after a sync. Every event has a
stable key; a key is stored in `notifications` once its message was delivered,
so nothing is sent twice. On the very first run all existing items are marked
as known ("seeded") instead of flooding the chat; only upcoming deadlines are sent.
"""
import html
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import db, telegram

DEADLINE_WINDOW = timedelta(hours=24)
DUE_FORMAT = "%Y-%m-%d %H:%M"  # as shown on eClass assignment pages


def _tz():
    return ZoneInfo(os.getenv("ECLASS_TZ", "Asia/Tashkent"))


def _e(text):
    return html.escape(text or "", quote=False)


def is_submitted(status):
    s = (status or "").lower()
    return s.startswith("submitted") or "does not require" in s


def parse_due(value):
    try:
        return datetime.strptime(value, DUE_FORMAT).replace(tzinfo=_tz())
    except (TypeError, ValueError):
        return None


def _left(delta):
    hours, rem = divmod(int(delta.total_seconds()) // 60, 60)
    return f"{hours} soat {rem} daqiqa" if hours else f"{rem} daqiqa"


def collect_events(conn, now):
    """Return every current event as {key, kind, course, text}; filtering happens later."""
    events = []
    known = db.notified_keys(conn)

    for r in conn.execute(
        """SELECT f.activity_id, f.filename, f.sha256, a.name, c.name AS course
           FROM files f JOIN activities a ON a.id = f.activity_id
           JOIN courses c ON c.id = a.course_id
           WHERE a.type != 'assign' ORDER BY c.name, a.section, a.id"""
    ):
        prefix = f"file:{r['activity_id']}:{r['filename']}:"
        updated = any(k.startswith(prefix) for k in known)
        label = _e(r["name"])
        if r["filename"] != r["name"]:
            label += f" — <i>{_e(r['filename'])}</i>"
        events.append({"key": prefix + r["sha256"], "kind": "material", "course": r["course"],
                       "text": label + (" (yangilandi)" if updated else "")})

    for r in conn.execute(
        """SELECT a.id, a.name, a.url, c.name AS course FROM activities a
           JOIN courses c ON c.id = a.course_id WHERE a.type = 'url'
           ORDER BY c.name, a.section, a.id"""
    ):
        events.append({"key": f"url:{r['id']}", "kind": "material", "course": r["course"],
                       "text": f'🎬 <a href="{html.escape(r["url"] or "")}">{_e(r["name"])}</a>'})

    for r in conn.execute(
        """SELECT s.*, a.name, c.name AS course,
                  (SELECT COUNT(*) FROM files f WHERE f.activity_id = a.id) AS n_files
           FROM assignments s JOIN activities a ON a.id = s.activity_id
           JOIN courses c ON c.id = a.course_id ORDER BY s.due_date, a.id"""
    ):
        aid, name = r["activity_id"], _e(r["name"])
        due_text = r["due_date"] or "muddat ko'rsatilmagan"
        attach = f", {r['n_files']} ta fayl" if r["n_files"] else ""
        events.append({"key": f"assign:{aid}", "kind": "assign", "course": r["course"],
                       "text": f"{name} — muddat: {_e(due_text)}{attach}"})
        if r["grade"]:
            events.append({"key": f"grade:{aid}:{r['grade']}", "kind": "grade", "course": r["course"],
                           "text": f"{name}: <b>{_e(r['grade'])}</b>"})
        due = parse_due(r["due_date"])
        if due and not is_submitted(r["submission_status"]) and now < due <= now + DEADLINE_WINDOW:
            events.append({"key": f"deadline:{aid}:{r['due_date']}", "kind": "deadline",
                           "course": r["course"],
                           "text": f"{name} — {_e(r['due_date'])} (<b>{_left(due - now)}</b> qoldi), "
                                   f"holat: {_e(r['submission_status'])}"})
    return events


SECTIONS = [
    ("deadline", "⏰ <b>Muddat yaqin — topshirilmagan!</b>"),
    ("assign", "📝 <b>Yangi topshiriqlar</b>"),
    ("grade", "🎓 <b>Yangi baholar</b>"),
    ("material", "📚 <b>Yangi materiallar</b>"),
]


def build_messages(events):
    """Group events into HTML messages under Telegram's size limit: [(text, keys)]."""
    lines = []  # (line, key or None)
    for kind, header in SECTIONS:
        group = [e for e in events if e["kind"] == kind]
        if not group:
            continue
        if lines:
            lines.append(("", None))
        lines.append((header, None))
        course = None
        for e in group:
            if e["course"] != course:
                course = e["course"]
                lines.append((f"<b>{_e(course)}</b>", None))
            lines.append((f"• {e['text']}", e["key"]))

    messages, text, keys = [], "", []
    for line, key in lines:
        if text and len(text) + len(line) + 1 > telegram.MAX_LEN:
            messages.append((text, keys))
            text, keys = "", []
        text = f"{text}\n{line}" if text else line
        if key:
            keys.append(key)
    if keys:
        messages.append((text, keys))
    return messages


def run(conn, dry_run=False, now=None):
    """Send pending notifications. Returns a short status string."""
    now = now or datetime.now(_tz())
    known = db.notified_keys(conn)
    events = [e for e in collect_events(conn, now) if e["key"] not in known]

    note = ""
    if not known:  # first run: remember what already exists, send only urgent deadlines
        baseline = [e["key"] for e in events if e["kind"] != "deadline"]
        if not dry_run:
            db.mark_notified(conn, baseline, seeded=True)
        note = f"; first run: {len(baseline)} existing items marked as known"
        events = [e for e in events if e["kind"] == "deadline"]

    messages = build_messages(events)
    if not messages:
        return f"notifications: nothing new{note}"

    token, chat_id = telegram.config()
    if dry_run or not (token and chat_id):
        reason = "dry run" if dry_run else "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set"
        for text, _ in messages:
            print(f"--- message ({reason}) ---\n{text}")
        return f"notifications: {len(events)} pending, not sent ({reason}){note}"

    sent = 0
    for text, keys in messages:
        telegram.send_message(token, chat_id, text)
        db.mark_notified(conn, keys)
        sent += len(keys)
    return f"notifications: sent {sent} events in {len(messages)} message(s){note}"
