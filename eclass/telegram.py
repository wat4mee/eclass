"""Minimal Telegram Bot API client (plain HTTP). The bot token is never printed."""
import os

import requests
from dotenv import load_dotenv

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000  # Telegram limit is 4096 characters per message


class TelegramError(RuntimeError):
    pass


def config():
    """Return (token, chat_id); either may be None if not configured."""
    load_dotenv()
    return os.getenv("TELEGRAM_BOT_TOKEN") or None, os.getenv("TELEGRAM_CHAT_ID") or None


def _call(token, method, **params):
    # requests' exception texts contain the URL (and thus the token): never let them escape.
    try:
        resp = requests.post(API.format(token=token, method=method), data=params, timeout=30)
        body = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise TelegramError(f"{method}: {type(exc).__name__}") from None
    if not body.get("ok"):
        raise TelegramError(f"{method}: {body.get('error_code')} {body.get('description')}")
    return body["result"]


def send_message(token, chat_id, text):
    _call(token, "sendMessage", chat_id=chat_id, text=text,
          parse_mode="HTML", disable_web_page_preview="true")


def get_chat_ids(token):
    """Chats that recently messaged the bot: [(chat_id, title)]."""
    chats = {}
    for upd in _call(token, "getUpdates"):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat")
        if chat:
            title = chat.get("title") or " ".join(
                filter(None, [chat.get("first_name"), chat.get("last_name")])
            )
            chats[chat["id"]] = title or chat.get("username") or ""
    return sorted(chats.items())
