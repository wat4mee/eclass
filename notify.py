"""Send pending eClass notifications to Telegram (no eClass requests).

    python notify.py             # send whatever is pending in the database
    python notify.py --dry-run   # print the messages instead of sending
    python notify.py --chat-id   # list chats that messaged the bot (to fill TELEGRAM_CHAT_ID)
    python notify.py --test      # send a test message (with your unsubmitted assignments)
"""
import argparse
import html
import sys

from eclass import db, notify, telegram
from eclass.config import DB_PATH



def test_message(conn):
    rows = conn.execute(
        """SELECT a.name, c.name AS course, s.due_date, s.submission_status
           FROM assignments s JOIN activities a ON a.id = s.activity_id
           JOIN courses c ON c.id = a.course_id ORDER BY s.due_date IS NULL, s.due_date"""
    ).fetchall()
    pending = [r for r in rows if not notify.is_submitted(r["submission_status"])]
    lines = [notify._t("tg.test.title"), notify._t("tg.test.body")]
    if pending:
        lines += ["", notify._t("tg.test.pending")]
        lines += [f"• {html.escape(r['course'])} — {html.escape(r['name'])} "
                  f"({html.escape(r['due_date'] or notify._t('tg.no_due_short'))})" for r in pending]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print messages, send nothing, mark nothing")
    ap.add_argument("--chat-id", action="store_true", help="show chat ids that recently messaged the bot")
    ap.add_argument("--test", action="store_true", help="send a test message to TELEGRAM_CHAT_ID")
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()

    if args.chat_id:
        token, _ = telegram.config()
        if not token:
            ap.error("TELEGRAM_BOT_TOKEN is not set in .env")
        chats = telegram.get_chat_ids(token)
        if not chats:
            print("No chats yet: send any message to your bot in Telegram, then rerun.")
        for chat_id, title in chats:
            print(f"{chat_id}\t{title}")
        return 0

    conn = db.connect(args.db)
    if args.test:
        token, chat_id = telegram.config()
        if not (token and chat_id):
            ap.error("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env")
        try:
            telegram.send_message(token, chat_id, test_message(conn))
        except telegram.TelegramError as exc:
            print(f"telegram error: {exc}", file=sys.stderr)
            return 1
        print("test message sent")
        return 0
    try:
        print(notify.run(conn, dry_run=args.dry_run))
    except telegram.TelegramError as exc:
        print(f"telegram error: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
