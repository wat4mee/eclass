# Loyiha holati: eClass Companion va sclass

Holat: **2026-09-30**, branch `hosted`. Testlar: **191 ta, hammasi o'tadi**.

Loyiha ikki qismdan iborat, ikkalasi `eclass/` kutubxonasini ishlatadi:
- **Mac versiya (bir foydalanuvchi):** `app.py` dashboard (127.0.0.1:5050), SQLite, launchd. `main` branch'da ham bor.
- **sclass (ko'p talabali sayt):** `web/` paketi, Postgres (Neon), Render. Faqat `hosted` branch'da.
  Hozir `https://eclass-zrs8.onrender.com` da ishlab turibdi (bepul tarif, Singapore).

## 1. Fayl tuzilmasi

`tree` o'rnatilmagan, ro'yxat `git ls-files` asosida. `tests/fixtures/` (namuna HTML), `static/katex/` va
`static/fonts/` (jami 75 fayl) ko'rsatilmagan.

```
eclass/                                  repo ildizi
├── app.py  sync.py  notify.py           Mac: dashboard, sinxronlash, Telegram eslatmalar
├── analyze.py  ask.py                   Mac: o'quv to'plamlari va chat (CLI)
├── eclass/                              umumiy kutubxona
│   ├── auth.py  courses.py  activities.py  files.py        eClass bilan ishlash
│   ├── extract.py  study.py  chapters.py  videos.py        matn va AI materiallar
│   ├── ai.py  rag.py  search.py  latex.py                  AI zanjiri, chat, qidiruv
│   ├── db.py  config.py  i18n.py  grades.py                 baza, sozlamalar, tillar
│   └── notify.py  telegram.py  syncstatus.py  lock.py       eslatmalar, holat, lock
├── web/                                 sclass sayti
│   ├── __init__.py  config.py  extensions.py  db.py  models.py
│   ├── crypto.py  redact.py  eclass_login.py  users.py  autosync.py
│   ├── sync.py  tasks.py  dashboard.py  search.py  packs.py  i18n.py
│   ├── views/  __init__.py  auth.py  account.py  dashboard.py  ask.py  pages.py
│   └── templates/  base login home course grades study ask account privacy reconnect error (.html)
├── templates/                           Mac shablonlari: base index course grades study book ask error
├── static/web/                          sayt: site.css  site.js  theme.js  ask.js  study.js
├── migrations/                          Alembic: env.py, versions/20260929_9badf696a03d_initial_schema.py
├── tests/                               Mac testlari + tests/web/ (sayt, Postgres bilan) + e2e.py (Playwright)
├── deploy/                              launchd: com.eclass.{sync,notify,web}.plist, install.sh, uninstall.sh
├── render.yaml  .github/workflows/sync-cron.yml  .python-version  alembic.ini  pytest.ini
├── requirements.txt  requirements-web.txt  requirements-dev.txt  .env.example
└── README.md  QOLLANMA.md  DEPLOY.md  CHANGELOG.md  CLAUDE.md
```

## 2. Asosiy Python fayllar

**Mac skriptlari**
- `app.py`: Mac dashboard (Flask). Bosh sahifa, kurslar, baholar, o'quv to'plamlari, boblar, chat, qidiruv, sync
  tugmasi. Yordamchilar: `deadline` (holat va qolgan vaqt), `week_info`, `all_assignments`, `plan_for_today`,
  `sync_history`, `ai_failure` (AI xatosini tushunarli xabarga aylantirish), `question_suggestions`.
- `sync.py`: eClass'dan kurslar, faoliyatlar va fayllarni yuklab SQLite'ga yozadi (`main`, `sync_course`, `run`).
- `notify.py`: muddat, yangi material va baho haqida Telegram xabarlari (`main`, `--test`).
- `analyze.py`: matn chiqarish va o'quv to'plamlarini yaratish (`main`, `print_plan`). `ask.py`: chat CLI.

**`eclass/` kutubxonasi**
- `auth.py`: `EClassClient` (login, sessiya, 1 so'rov/soniya, qayta kirish, cookie eksporti); xato turlari
  `EClassError` → `LoginError`, `SessionExpired`, `NetworkError`, `EClassTimeout`, `ServerError`, `PageError`.
- `courses.py` (`list_courses`, `parse_course_page`), `activities.py` (`parse_activity`, `parse_assign`,
  `pluginfile_links`, `resolve_url`), `files.py` (fayl nomi, sha256, yuklash): eClass sahifalarini tahlil qilish.
- `extract.py`: PDF/PPTX/DOCX dan matn (`extract_pdf/pptx/docx`, `extract_bytes`, Mac'da OCR).
- `ai.py`: Groq, Gemini, Ollama provayderlari va `ChainProvider` (limit tugasa keyingisiga o'tadi); `get_provider`.
- `rag.py`: chat (`answer`: savolni qayta yozish, qidiruv, manbali javob, `clean_answer`); Mac'da embedding indeksi.
- `study.py`: xulosa, kartalar, test (`build_pack`, `chunk_pages`, `generate_pending`, `translate_pack`).
- `chapters.py` (darsliklarni boblarga bo'lish), `videos.py` (YouTube transkript), `search.py` (FTS5, ⌘K).
- `db.py`: SQLite sxemasi va yozish funksiyalari (`upsert_*`, `save_study`, `start/finish_sync_run`).
- `config.py`, `i18n.py` (uz/en/ru matnlar, `t`, `plural`, sanalar), `grades.py`, `latex.py` (JSON buzgan LaTeX'ni
  tiklash), `notify.py`, `telegram.py`, `syncstatus.py`, `lock.py` (bir vaqtda bitta sync).

**`web/` (sclass)**
- `__init__.py`: `create_app` (sozlamalar, CSRF, rate limit, login, host tekshiruvi, xavfsizlik sarlavhalari, CSP,
  xato sahifalari, `rotate-credentials` buyrug'i); `FirstForwardedFor` (Render'da haqiqiy IP).
- `config.py`: muhit o'zgaruvchilaridan sozlamalar (`from_env`, `database_url`, `allowed_hosts`).
- `models.py`: SQLAlchemy modellari (4-bo'lim). `db.py`: engine va so'rov sessiyasi.
- `eclass_login.py`: proksi login (`check_login`), eClass sessiyasini shifrlab saqlash/o'qish (`save/load/drop_session`).
- `crypto.py`: Fernet (`encrypt`, `decrypt`, kalit versiyalari, `rotate`). `redact.py`: loglarda parol/cookie/token yashirish.
- `autosync.py`: fonda sinxronlash uchun parolni saqlash/o'chirish (`enable`, `disable`, `state`).
- `sync.py`: bitta talabani sinxronlash (`sync_user`, advisory lock, fayllar xotirada o'qiladi); `run_all` (cron:
  talabalarni birma-bir, tanaffus va backoff bilan); `reap`/`is_running` (o'lgan sync'ni aniqlash); `main` (CLI).
- `tasks.py`: sayt ichida sync navbati, bitta ishchi thread (`start_sync`, `start_sync_all`, `waiting`).
- `dashboard.py`: sahifa ma'lumotlari (kurslar, topshiriqlar, baholar, haftalar, statistika), hammasi enrollment orqali.
- `packs.py`: o'quv to'plamlari (`generate_pending` Gemini limiti ichida, `pack_for`, `with_packs`).
- `search.py`: Postgres full-text qidiruv (`passages`). `users.py`: `signed_in`, `delete_user`. `i18n.py`: sayt matnlari.
- `views/`: `auth` (login, reconnect, logout), `account` (hisob, fonda sync on/off, o'chirish), `dashboard` (sahifalar,
  fayl, sync), `ask` (chat, kunlik limit), `pages` (maxfiylik), `internal` (`/internal/sync-all`, Bearer token).

## 3. requirements.txt

```
beautifulsoup4==4.15.0
fastembed==0.8.1
flask==3.1.3
numpy==2.5.3
ocrmac==1.0.1; sys_platform == "darwin"
pillow==12.3.0
pymupdf==1.28.2
python-docx==1.2.0
python-dotenv==1.2.3
python-pptx==1.0.2
requests==2.34.2
youtube-transcript-api==1.2.4
```

`requirements-web.txt` (Render): alembic 1.20.0, beautifulsoup4 4.15.0, cryptography 50.0.1, flask 3.1.3,
flask-limiter 4.1.1, flask-login 0.6.3, flask-wtf 1.3.0, gunicorn 26.2.0, numpy 2.5.3, psycopg[binary] 3.3.6,
pymupdf 1.28.2, python-docx 1.2.0, python-dotenv 1.2.3, python-pptx 1.0.2, requests 2.34.2, sqlalchemy 2.1.1.
`requirements-dev.txt`: `-r requirements.txt`, playwright 1.63.0, pytest 9.1.1.

## 4. Ma'lumotlar bazasi

**Mac: SQLite (`data/eclass.db`)**
- `courses` (id, name, code, professor, first_seen, last_seen); `sections` (course_id, number, name, ...)
- `activities` (id, course_id, section, type, name, url, ...); `files` (id, activity_id, filename, path, sha256, size, downloaded_at, source_url)
- `assignments` (activity_id, due_date, submission_status, grading_status, grade, intro, updated_at)
- `extractions` (file_id, sha256, method, n_pages, n_chars, error); `pages` (file_id, page, text)
- `study` (file_id, sha256, provider, model, language, summary, concepts, flashcards, quiz); `study_notes`; `study_i18n`
- `chunks` (id, file_id, sha256, page, text, embedding) + `chunks_fts` (FTS5); `index_state`; `search_fts` (⌘K)
- `chapters` (file_id, idx, title, start_page, end_page, pack maydonlari); `videos` (activity_id, video_id, status, ...)
- `progress` (file_id, studied_at); `notifications` (key, sent_at, seeded); `sync_runs` (id, vaqtlar, started_by, state, code, detail, new_items, errors)

**sclass: Postgres (Alembic, bitta migratsiya `9badf696a03d`)** (`*` = birlamchi kalit)
- Shaxsiy (foydalanuvchi o'chirilsa CASCADE):
  - `users` (id*, eclass_username, display_name, created_at, last_login_at)
  - `eclass_credentials` (user_id*, encrypted_password, key_version, autosync_enabled, status, last_verified_at, updated_at)
  - `eclass_sessions` (user_id*, encrypted_cookie, key_version, created_at, expires_at)
  - `enrollments` (user_id*, course_id*, last_seen_at)
  - `user_assignments` (user_id*, activity_id*, due_at, due_text, submission_status, grading_status, grade, updated_at)
  - `progress` (user_id*, material_id*, studied_at)
  - `sync_runs` (id*, user_id, trigger, started_at, finished_at, status, error_code, error_summary, new_items, errors)
  - `ai_usage` (user_id*, day*, count)
- Kurs bo'yicha umumiy (talabalar bo'lishadi):
  - `courses` (id*, name, code, professor, first_seen_at, last_seen_at); `sections` (course_id*, number*, name)
  - `activities` (id*, course_id, section, type, name, url, intro, first_seen_at, last_seen_at)
  - `materials` (id*, activity_id, filename, eclass_url, sha256, size, mimetype, n_pages, n_chars, extract_error, extracted_at, first_seen_at)
  - `material_pages` (material_id*, page*, text, tsv + GIN indeks)
  - `study_packs` (id*, material_id, sha256, language, provider, model, summary, concepts, flashcards, quiz, created_at)
  - `pack_notes` (material_id*, sha256*, chunk*, notes)

## 5. Flask route'lar

**sclass (`web/`)**

| URL | Metod | Vazifasi |
|---|---|---|
| `/login` | GET, POST | eClass login bilan kirish (proksi login), "fonda sinxronlab tur" belgisi |
| `/reconnect` | GET, POST | eClass sessiyasi tugaganda parolni qayta kiritish |
| `/logout` | POST | chiqish, eClass sessiyasini o'chirish |
| `/` | GET | bosh sahifa: muddat halqasi, statistika, topshiriqlar, baholar, materiallar, kurslar |
| `/course/<id>` | GET | kurs: haftalar, faoliyatlar, fayllar, topshiriq holati |
| `/grades` | GET | baholar kurs bo'yicha |
| `/study/<material_id>` | GET | o'quv to'plami: xulosa, kartalar, test |
| `/api/studied/<material_id>` | POST | "o'rganildi" belgisi (JSON, CSRF sarlavhasi) |
| `/file/<material_id>` | GET | faylni talabaning eClass sessiyasi orqali oqim bilan berish (saqlanmaydi) |
| `/sync` | POST | sinxronlashni navbatga qo'yish (3/daqiqa) |
| `/sync/status` | GET | sinxronlash holati (JSON) |
| `/ask` | GET | Shahzod AI sahifasi |
| `/api/ask` | POST | chat javobi (JSON, kunlik limit) |
| `/account` | GET | hisob, fonda sinxronlash, ma'lumotlarni o'chirish |
| `/account/autosync` | POST | fonda sinxronlashni yoqish (parol tekshiriladi) |
| `/account/autosync/off` | POST | o'chirish, parolni darhol o'chirish |
| `/account/delete` | POST | "Ulanishni uzish va ma'lumotlarimni o'chirish" |
| `/privacy` | GET | maxfiylik sahifasi (ochiq) |
| `/healthz` | GET | Render health check |
| `/internal/sync-all` | POST | GitHub Actions: hammani fonda sinxronlash (Bearer `CRON_SECRET`, 1/daqiqa, 202) |

**Mac (`app.py`)**: `/`, `/course/<id>`, `/grades`, `/study/<file_id>`, `/study/<file_id>/ch/<idx>`, `/book/<file_id>`,
`/ask`, `/file/<file_id>` (GET); `/api/ask`, `/api/studied/<id>`, `/api/translate/<id>`, `/api/sync` (POST);
`/api/chapter/<id>/<idx>` (GET, POST); `/api/search`, `/api/sync/status` (GET).

## 6. .env.example (to'liq; haqiqiy qiymatlar faqat `.env` da)

```
# eClass login
ECLASS_USER=
ECLASS_PASS=

# AI: auto = Groq models -> Gemini (if key) -> Ollama (if running); or e.g. "gemini,groq"
AI_PROVIDER=auto
GROQ_API_KEY=
# free key: https://aistudio.google.com/apikey (free tier data is used by Google to improve products)
GEMINI_API_KEY=
# GROQ_MODEL=openai/gpt-oss-120b

# Telegram notifications (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# --- Optional settings (values below are the defaults) ---
# STUDY_LANGUAGE=uz        # study pack language: uz | en | ru
# ECLASS_TZ=Asia/Tashkent  # time zone for deadline reminders
# EMBED_THREADS=2          # CPU cores for the search index (0 = all)
# FLASK_DEBUG=0            # 1 = Flask debug mode (keep off)
# GROQ_TPM=8000            # Groq tokens/minute to pace for (free tier)
# GEMINI_MODEL=gemini-3.5-flash-lite
# OLLAMA_URL=http://localhost:11434
# OLLAMA_MODEL=qwen3:14b
# OLLAMA_TIMEOUT=900        # seconds per request to a local Ollama model
# AI_FALLBACK=              # models tried last when every AI_PROVIDER model fails or is too slow;
#                           # same format as AI_PROVIDER, e.g. groq:openai/gpt-oss-120b,ollama
# AI_TIMEOUT=180            # seconds per AI request for study packs and chapters
# AI_CHAT_TIMEOUT=30        # seconds per AI request in the chat (a slower model is skipped)
# AI_CHAT_BUDGET=75         # seconds for a whole chat answer
# ECLASS_TIMEOUT=60         # seconds per eClass request
# NOTIFY_LANGUAGE=uz        # Telegram message language: uz | en | ru

# ---- sclass: the hosted multi-user site (web/). On Render these come from render.yaml and the dashboard
# (DEPLOY.md); locally only the first two are useful. Never commit real values.
# CREDENTIAL_KEY=           # Fernet key for stored eClass passwords; generate: see DEPLOY.md, step 2
# SECRET_KEY=               # signs login cookies (any long random string)
# DATABASE_URL=             # default: local Postgres database eclass_web_dev
# CREDENTIAL_KEY_VERSION=1  # raise by 1 when rotating; the old key goes to CREDENTIAL_KEY_PREVIOUS
# CREDENTIAL_KEY_PREVIOUS=
# HOSTED=0                  # 1 on Render: every secret required, HTTPS-only cookies
# ALLOWED_HOSTS=            # extra host names (custom domain); Render's own name is allowed automatically
# AI_DAILY_LIMIT=30         # chat questions per student per day
# STUDY_LANGUAGE=uz         # language of study packs
# PACKS_PER_RUN=6           # study packs per background run
# SYNC_PAUSE_SECONDS=20     # pause between students in a background run
# ECLASS_SESSION_MINUTES=120
# GitHub Actions orqali /internal/sync-all ni chaqirish uchun tasodifiy uzun matn; generatsiya: python -c "import secrets; print(secrets.token_urlsafe(32))"
CRON_SECRET=
```

## 7. Ishga tushirish

**Mac versiya**
- Development: `.venv/bin/pip install -r requirements-dev.txt`, `.venv/bin/python app.py` → http://127.0.0.1:5050
- Doimiy: `./deploy/install.sh` (launchd: sync har 3 soatda, eslatmalar har 30 daqiqada, dashboard doim yoqiq).

**sclass, development**
- `brew services run postgresql@16`, `createdb eclass_web_dev`, `.venv/bin/pip install -r requirements-web.txt`
- `.venv/bin/alembic upgrade head`, `.venv/bin/flask --app web run` (`.env` da mahalliy `CREDENTIAL_KEY`, `SECRET_KEY` bor)
- Fon sinxronlash qo'lda: `.venv/bin/python -m web.sync --all`; o'quv to'plamlari: `--packs N`.

**sclass, production (Render + Neon)**: batafsil `DEPLOY.md`
- Build: `pip install -r requirements-web.txt`
- Start: `alembic upgrade head && gunicorn --workers 1 --threads 8 --timeout 120 --bind 0.0.0.0:$PORT "web:create_app()"`
- Fon sinxronlash: GitHub Actions (`sync-cron.yml`) har 3 soatda `POST /internal/sync-all` (bepul); `render.yaml` cron'i pullik tarif uchun.
- Kalit almashtirish: `flask --app web rotate-credentials`.

**Testlar**: `.venv/bin/pytest` (191 ta; `tests/web` uchun `eclass_web_test` bazasi kerak), `tests/e2e.py` (Playwright).

## 8. CHANGELOG.md: so'nggi 10 ta yozuv

`CHANGELOG.md` da sclass ishi (milestone 1–5) hali yozilmagan. Undagi eng yangi 10 ta yozuv (2026-09-29):
1. Topilgan ikki jiddiy xato: KaTeX formulalari buzilishi (`eclass/latex.py`) va `found=true` sizib chiqishi.
2. Kod sifati: `eclass/config.py`, N+1 so'rovlar, xatolarni bir xil ko'rsatish.
3. Testlar: 68 ta pytest, testlar topgan 3 ta xato tuzatildi.
4. Ishonchlilik: xato turlari, bitta kurs buzilsa qolganlari davom etadi, `sync_runs` tarixi, AI vaqt chegaralari.
5. Xavfsizlik tekshiruvi (2): X-Frame-Options, `data/` 700, versiyalar qulflandi.
6. Tanlangan sukut qiymatlar (AI_FALLBACK bo'sh, chat 30/75 soniya, Telegram tili `uz`).
7. "Keyingi safar e'tibor bering": launchd qayta ishga tushirish, push, kalitlarni almashtirish, CSP.
8. Tillar (uz/en/ru) va Shahzod AI nomi.
9. AI chat: suhbat xotirasi, manbalar, xatolarni ushlash, formulalar.
10. Sinxronlash tugmasi, launchd agentlari va Telegram eslatmalar.

Git'dagi eng yangi commit'lar (sclass): `abc8afa` bitta vaqtda bitta sync, o'lgan sync osilib qolmaydi; `20671c8`
Render (5); `a2d212a` fonda sync, cron, o'quv to'plamlari, kalit almashtirish (4); `91a326f` talaba sahifalari, chat,
Mac dizayni (3); `474aaa5` proksi login va xavfsizlik (2); `4bb565c` modellar va migratsiyalar (1).

## 9. Ma'lum muammolar va tugallanmagan ishlar

Kodda `TODO`/`FIXME` izohlari yo'q.

- **Render bepul tarifi:** 0.1 CPU va 512 MB. Birinchi sinxronlashlarda sayt sekinlashadi; bir necha talaba bir vaqtda
  kirganda jarayon qayta ishga tushgan (ehtimol xotira). `abc8afa` bilan navbat qo'shildi, natijasi hali kuzatilmagan.
  Ko'p talaba bo'lsa, pullik `0.5c-512mb` tarif tavsiya qilinadi.
- **Neon regioni noma'lum:** Render Singapore'da. Region boshqa bo'lsa, har so'rov sekinlashadi.
- **GitHub Actions** sozlanishi kerak: `CRON_SECRET` (Render + GitHub), `RENDER_URL`, workflow default branch'da (DEPLOY.md, 9).
- **Bir xil fayl turli eClass kurslarida** (guruhlar alohida kurs bo'lsa) ikki marta saqlanadi va to'plam ikki marta
  yaratiladi. sha256 bo'yicha birlashtirish taklif qilingan, Neon'dagi real ma'lumot kutilmoqda.
- **Saytda yo'q (Mac'da bor):** darslik boblari, YouTube transkriptlar, to'plam tarjimasi, Telegram, ⌘K qidiruv,
  OCR (Render Linux), embedding qidiruv (sayt Postgres full-text ishlatadi).
- `CHANGELOG.md` va `CLAUDE.md` sclass ishi bilan yangilanmagan.
- `pip-audit` ishga tushirilmagan. Mac dashboard'da CSP yo'q (inline skriptlar ko'p). Mac Flask dev server'da ishlaydi.
- Groq, Telegram va Gemini kalitlari avval chatga yozilgan: almashtirish tavsiya qilinadi.
- Qolib ketgan worktree: `git worktree remove .claude/worktrees/agent-ae49f5bc79c3290f8 && git branch -D pro-upgrade`.
- Talabalarni taklif qilishdan oldin INHA IT ruxsati so'ralmagan. eClass Render IP'sini cheklashi mumkin.

## 10. Xavfsizlik holati

**Mac versiya:** autentifikatsiya yo'q, chunki faqat 127.0.0.1 da ishlaydi. Host tekshiruvi (DNS rebinding),
POST'larda Origin/Referer va faqat JSON (CSRF o'rniga), X-Frame-Options, nosniff. Sirlar faqat `.env` da.

**sclass:**
- **Kirish:** proksi login. Login va parol eClass'ga kirib tekshiriladi; parol odatda saqlanmaydi. Sessiya Flask-Login
  (14 kunlik "remember me"). eClass sessiya cookie'si Fernet bilan shifrlanib ko'pi bilan 2 soat saqlanadi.
- **Parol saqlash (ixtiyoriy):** "fonda sinxronlab tur" belgilansa, Fernet bilan shifrlanadi, `key_version` bilan.
  Faqat `web/sync.py` da ochiladi (test tekshiradi). eClass rad etsa, darhol o'chiriladi (akkaunt bloklanmasligi uchun).
- **Kalit:** `CREDENTIAL_KEY` faqat muhitda; `rotate-credentials` buyrug'i va `CREDENTIAL_KEY_PREVIOUS` bilan almashtiriladi.
- **CSRF:** Flask-WTF, har bir forma va JSON POST (`X-CSRFToken`). `/internal/sync-all`: CSRF o'rniga Bearer token (`hmac.compare_digest`).
- **Rate limit:** login IP bo'yicha 10/daqiqa va 60/soat, username bo'yicha 5/15 daqiqa; `/sync` 3/daqiqa; AI 30 savol/kun.
- **Cookie'lar:** Secure, HttpOnly, SameSite=Lax. **Sarlavhalar:** qat'iy CSP (inline skript yo'q), HSTS,
  X-Frame-Options DENY, nosniff, Referrer-Policy. Host allowlist.
- **Loglar:** parol, cookie, token va Fernet qiymatlari yashiriladi (test bilan).
- **Ma'lumotlarni ajratish:** har bir so'rov enrollment orqali; boshqa talabaning kursi va fayli 404. Fayllar faqat eClass
  domenidan, HTML fayllar yuklab olish sifatida beriladi. Havolalar faqat http(s).
- **Talaba huquqlari:** "ma'lumotlarimni o'chirish" (hammasi o'chadi), `/privacy` sahifasi, "norasmiy loyiha" belgisi.

**Hali qilinmagan:**
- rate limit xotirada: faqat bitta gunicorn worker. Ko'paytirish uchun Redis kerak;
- monitoring va ogohlantirishlar yo'q; zaxira nusxa Neon imkoniyatiga bog'liq;
- `pip-audit` qilinmagan;
- INHA IT roziligi olinmagan.
