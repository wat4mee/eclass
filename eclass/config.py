"""Paths, URLs, time limits and other settings shared by the scripts, the dashboard and the eclass package.

Values that a user may want to change can be overridden in .env (names in the comments); everything else is
a named constant here instead of a number scattered through the code.
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def env_int(name: str, default: int) -> int:
    """Integer setting from .env; a missing or malformed value falls back to the default."""
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


# ---------------------------------------------------------------- storage
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "eclass.db"
FILES_DIR = DATA_DIR / "files"
MODEL_DIR = DATA_DIR / "models"         # local embedding model cache
LOG_DIR = DATA_DIR / "logs"
RUN_LOCK = DATA_DIR / ".run.lock"       # one sync/analyze run at a time

# ---------------------------------------------------------------- eClass
ECLASS_URL = "https://eclass.inha.ac.kr"
ECLASS_MIN_INTERVAL = 1.0               # seconds between requests: be polite to the university server
ECLASS_TIMEOUT = env_int("ECLASS_TIMEOUT", 60)          # seconds per eClass request

# ---------------------------------------------------------------- AI
AI_TIMEOUT = env_int("AI_TIMEOUT", 180)                 # seconds per AI request (study packs, chapters)
AI_CHAT_TIMEOUT = env_int("AI_CHAT_TIMEOUT", 30)        # seconds per AI request while the student waits in chat:
                                                        # a slower model is skipped for the next one in the chain
AI_CHAT_BUDGET = env_int("AI_CHAT_BUDGET", 75)          # seconds for a whole chat answer (the page waits 15 s more)
OLLAMA_TIMEOUT = env_int("OLLAMA_TIMEOUT", 900)         # local models are slow on a laptop CPU

# ---------------------------------------------------------------- Telegram
TELEGRAM_TIMEOUT = 30
NOTIFY_LANGUAGE = os.getenv("NOTIFY_LANGUAGE", "uz")   # language of Telegram messages: uz | en | ru

# ---------------------------------------------------------------- dashboard
SOON_WINDOW = timedelta(hours=48)       # an unsubmitted assignment due within this is shown as "soon"
DEADLINE_RING = timedelta(days=7)       # the countdown ring is full a week before a deadline
SYNC_FRESH = timedelta(hours=4)         # the sync dot is green while the last sync is younger than this
SYNC_START_GRACE = timedelta(seconds=20)  # a "running" status without a live process is stale after this
SYNC_HISTORY = 10                       # sync attempts kept for the dashboard
