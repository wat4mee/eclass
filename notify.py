"""Send pending eClass notifications to Telegram (no eClass requests).

    python notify.py             # send whatever is pending in the database
    python notify.py --dry-run   # print the messages instead of sending
    python notify.py --chat-id   # list chats that messaged the bot (to fill TELEGRAM_CHAT_ID)
"""
import argparse
import sys
from pathlib import Path

from eclass import db, notify, telegram

DATA_DIR = Path(__file__).resolve().parent / "data"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print messages, send nothing, mark nothing")
    ap.add_argument("--chat-id", action="store_true", help="show chat ids that recently messaged the bot")
    ap.add_argument("--db", default=str(DATA_DIR / "eclass.db"))
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
