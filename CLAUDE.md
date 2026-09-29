# eClass Companion — INHA University in Tashkent

Personal tool that auto-imports course materials from eClass (https://eclass.inha.ac.kr),
tracks deadlines/grades, and analyzes materials with AI. Personal use only, single user.

## Stack
- Python 3.11+, `requests` + `beautifulsoup4` (scraper), SQLite (via `sqlite3` or SQLAlchemy)
- Flask for the dashboard (owner already knows Flask)
- Text extraction: `pymupdf` (PDF), `python-pptx` (PPTX), `python-docx` (DOCX)
- AI provider is configurable via `.env`: `AI_PROVIDER=groq` (default; free tier, `openai/gpt-oss-120b`,
  limits 8K tokens/min and 200K tokens/day) or `AI_PROVIDER=ollama` (local)
- OCR for image-only PDF pages: macOS Vision via `ocrmac`
- Notifications: Telegram bot (`python-telegram-bot` or plain HTTP to Bot API)

## Credentials — IMPORTANT
- Read `ECLASS_USER` / `ECLASS_PASS` / `GROQ_API_KEY` / `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` from `.env` only
  (see `.env.example`).
- `.env` must be in `.gitignore`. Never print, log, or commit credentials.
- Never hardcode the password in code or tests.

## What we know about eClass (verified by inspecting the live site)
- Platform: **Moodle** with the Korean "Coursemos" theme (`M.cfg.theme = coursemosv2`).
  Custom modules: `ubfile` (file resource), `ubboard` (announcements / Q&A boards).
- Login page: `/login.php`, form posts to `/login/index.php` with `username`, `password`.
  The Coursemos form has **no `logintoken`** (forward whatever hidden inputs exist).
  Success = final page is not `/login*` and contains a `login/logout.php` link.
- The server drops connections that use the default `python-requests` User-Agent: send a custom UA.
- Session is cookie-based (`MoodleSession`). Keep one `requests.Session`.
- Moodle AJAX web services via browser session return `servicenotavailable` for
  `core_course_get_contents` -> **scrape HTML instead**.
- `tool_mobile_get_public_config` responds (typeoflogin=1), so the Moodle mobile token
  endpoint `/login/token.php?service=moodle_mobile_app` MAY work. Try it as an optional
  faster path; fall back to HTML scraping if it fails.

### Pages and structure
- Dashboard `/` : course links are `a[href*="course/view.php?id="]`.
  Current course ids: 2482 Academic English Reading, 2493 Academic English 1, 2539 Calculus 1,
  2544 Physics 1, 2554 Physics Experiment 1, 2562 OOP 1, 2596 Introduction to IT.
  (Always discover ids dynamically; don't hardcode.)
- Course page `/course/view.php?id=N`:
  - sections: `li.section` with id `section-N`, title `.sectionname` (e.g. "3Week [19 September - 25 September]").
    The current week is rendered twice (also at the top): de-duplicate by id.
  - activities: `li.activity` with id `module-N`, type from class `modtype_<type>`, name from `.instancename`
    minus its hidden `.accesshide` span
  - types seen: `ubfile`, `assign`, `url` (lecture videos), `folder`, `label`, `ubboard`
- `ubfile`: `/mod/ubfile/view.php?id=N` **redirects directly to the file**
  (`/pluginfile.php/<ctx>/mod_ubfile/content/0/<filename>`, e.g. `application/pdf`).
  Take the filename from the final URL / Content-Disposition.
- `folder`: `/mod/folder/view.php?id=N` — list of `pluginfile.php` links inside.
- `url`: `/mod/url/view.php?id=N` — store the external link (videos), don't download.
- `assign`: `/mod/assign/view.php?id=N`
  - description: `#intro` (may contain attachments `#intro a[href*="pluginfile"]`)
  - status table rows (`.submissionstatustable tr`, `.generaltable tr`): Submission status,
    Grading status, Due date (format `2026-09-25 15:00`), Time remaining, Last modified,
    File submissions, Submission comments, Grade (e.g. `22.00 / 25.00`)
- Upcoming events: `/calendar/view.php?view=upcoming` (`.event` elements).
  Calendar export form at `/calendar/export.php` -> can produce an .ics URL for deadlines.
- Announcements/Q&A: `mod/ubboard/view.php?id=N`, personal board list `mod/ubboard/my.php`.

## Features (build in this order)
1. **Scraper/sync** (`sync.py`): login -> list courses -> list activities -> download new files
   into `data/files/<course>/<section>/`, upsert everything into SQLite. Detect changes by
   activity id + file hash. Be polite: 1 request/sec, run at most every few hours.
2. **Change notifications**: new material, new assignment, deadline < 24h and not submitted,
   new grade -> Telegram message.
3. **Text extraction + AI**: for each new file extract text, then generate
   summary, key concepts, flashcards, 5-question practice quiz. Store results in DB.
4. **Course Q&A (RAG)**: chunk texts, local embeddings + keyword search, answer questions
   citing the source file/page.
5. **Flask dashboard**: deadlines timeline, per-course materials with summaries,
   grades table, "ask the course" chat.

## Conventions
- Language of UI/summaries: configurable, default Uzbek (Latin); materials are mostly English.
- Keep scraping logic in `eclass/` package, one module per concern (auth, courses, activities, files).
- Handle login expiry: if a response redirects to `/login`, re-login once and retry.

## Status (2026-09-29)
All 5 planned features are built, plus: UZ/EN/RU UI (`eclass/i18n.py`), Shahzod AI chat with memory and
filtered sources (`eclass/rag.py`), AI provider chain (`eclass/ai.py`, `AI_PROVIDER=auto`: Groq models ->
Gemini -> Ollama), textbook chapters on demand (`eclass/chapters.py`), YouTube transcripts (`eclass/videos.py`),
Cmd+K search (`eclass/search.py`, FTS5), sync status/button (`eclass/syncstatus.py`), today plan + studied flags,
error pages and a Host/Origin guard in `app.py`. See README.md (setup, launchd via `deploy/install.sh`, privacy)
and CHANGELOG.md (what changed, security review, open items). Browser checks: `tests/e2e.py` (Playwright).
